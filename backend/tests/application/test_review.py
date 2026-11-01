from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import get_session
from app.main import app
from app.models import FinancialCommitment
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf


def client_for(factory):
    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    return TestClient(app)


def upload(client, factory, **settings):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("unseen.pdf", invoice_pdf(**settings), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    run_once(factory)
    result = client.get("/api/v1/runs/" + response.json()["run_id"]).json()
    assert result["status"] == "SUCCEEDED", result
    return result


def test_correction_revalidates_preserves_history_and_metrics(workflow_db):
    factory = workflow_db
    try:
        with client_for(factory) as client:
            original = upload(client, factory, missing=True)
            assert original["outcome"] == "NEEDS_REVIEW"
            task = client.get("/api/v1/reviews").json()["tasks"][0]
            response = client.post(
                f"/api/v1/reviews/{task['id']}/corrections",
                json={
                    "version": task["version"],
                    "comment": "Invoice number verified against the synthetic vendor record.",
                    "values": {"invoice_number": "CORRECTED-001"},
                },
            )
            assert response.status_code == 202, response.text
            run_once(factory)
            updated = client.get("/api/v1/runs/" + response.json()["run_id"]).json()
            assert updated["outcome"] == "VALIDATED", updated["decision"]["rules"]
            assert client.get("/api/v1/runs/" + original["id"]).json()["outcome"] == "NEEDS_REVIEW"
            review = client.get("/api/v1/reviews/" + task["id"]).json()
            assert (
                review["status"] == "RESOLVED"
                and len(review["corrections"]) == 1
                and len(review["decisions"]) == 2
            )
            metrics = client.get("/api/v1/dashboard").json()
            assert metrics["total_invoices"] == 1 and metrics["processing_runs"] == 2
            assert metrics["outcomes"]["VALIDATED"] == 1
            assert any(
                e["action"] == "CORRECTION_SAVED"
                for e in client.get("/api/v1/audit-events").json()["events"]
            )
    finally:
        app.dependency_overrides.clear()


def test_existing_reservation_held_replaced_without_double_consumption(workflow_db):
    factory = workflow_db
    try:
        with client_for(factory) as client:
            first = upload(client, factory, quantity="75", subtotal="1500", tax="150", total="1650")
            assert first["outcome"] == "VALIDATED"
            task = client.post("/api/v1/runs/" + first["id"] + "/review").json()
            with factory() as s:
                assert s.scalar(select(FinancialCommitment.status)) == "HELD"
            payload = {
                "version": task["version"],
                "comment": "Correct quantities and totals verified with vendor documentation.",
                "values": {"subtotal": "1600", "tax": "160", "total": "1760"},
                "items": [
                    {
                        "sku": "PAPER-A4",
                        "quantity": "80",
                        "unit_price": "20",
                        "net": "1600",
                        "tax_rate": "0.10",
                        "tax": "160",
                        "gross": "1760",
                    }
                ],
            }
            response = client.post("/api/v1/reviews/" + task["id"] + "/corrections", json=payload)
            assert response.status_code == 202, response.text
            run_once(factory)
            result = client.get("/api/v1/runs/" + response.json()["run_id"]).json()
            assert result["outcome"] == "VALIDATED", result["decision"]["rules"]
            with factory() as s:
                consuming = s.scalars(
                    select(FinancialCommitment).where(
                        FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"])
                    )
                ).all()
                assert len(consuming) == 1 and consuming[0].amount == Decimal("1760")
                assert (
                    s.scalar(
                        select(func.count())
                        .select_from(FinancialCommitment)
                        .where(FinancialCommitment.status == "RELEASED")
                    )
                    == 1
                )
    finally:
        app.dependency_overrides.clear()


def test_overbilling_correction_keeps_hold_until_explicit_release(workflow_db):
    factory = workflow_db
    try:
        with client_for(factory) as client:
            first = upload(client, factory)
            task = client.post("/api/v1/runs/" + first["id"] + "/review").json()
            response = client.post(
                "/api/v1/reviews/" + task["id"] + "/corrections",
                json={
                    "version": task["version"],
                    "comment": "Rechecking a supplier-requested increase against authorization.",
                    "values": {"subtotal": "3000", "tax": "300", "total": "3300"},
                    "items": [
                        {
                            "sku": "PAPER-A4",
                            "quantity": "150",
                            "unit_price": "20",
                            "net": "3000",
                            "tax_rate": "0.1",
                            "tax": "300",
                            "gross": "3300",
                        }
                    ],
                },
            )
            assert response.status_code == 202, response.text
            run_once(factory)
            result = client.get("/api/v1/runs/" + response.json()["run_id"]).json()
            assert result["outcome"] == "BLOCKED"
            with factory() as s:
                assert s.scalar(select(FinancialCommitment.status)) == "HELD"
            stale = client.post(
                "/api/v1/reviews/" + task["id"] + "/release",
                json={
                    "version": task["version"],
                    "comment": "Reject the supplier increase and release the prior hold.",
                },
            )
            assert stale.status_code == 409
            task = client.get("/api/v1/reviews/" + task["id"]).json()
            released = client.post(
                "/api/v1/reviews/" + task["id"] + "/release",
                json={
                    "version": task["version"],
                    "comment": "Reject the supplier increase and release the prior hold.",
                },
            )
            assert released.status_code == 200, released.text
            with factory() as s:
                assert s.scalar(select(FinancialCommitment.status)) == "RELEASED"
            assert client.get("/api/v1/dashboard").json()["outcomes"]["BLOCKED"] == 1
    finally:
        app.dependency_overrides.clear()


def test_no_verification_flag_injection_and_stale_correction(workflow_db):
    factory = workflow_db
    try:
        with client_for(factory) as client:
            upload(client, factory, missing=True)
            task = client.get("/api/v1/reviews").json()["tasks"][0]
            response = client.post(
                "/api/v1/reviews/" + task["id"] + "/corrections",
                json={
                    "version": task["version"],
                    "comment": "A proper review comment for field correction.",
                    "values": {"verified": "true"},
                },
            )
            assert response.status_code == 422
            payload = {
                "version": task["version"],
                "comment": "A proper review comment for field correction.",
                "values": {"invoice_number": "HUMAN-001"},
            }
            assert (
                client.post(
                    "/api/v1/reviews/" + task["id"] + "/corrections", json=payload
                ).status_code
                == 202
            )
            assert (
                client.post(
                    "/api/v1/reviews/" + task["id"] + "/corrections", json=payload
                ).status_code
                == 409
            )
    finally:
        app.dependency_overrides.clear()


def test_conflicting_duplicate_review_cannot_change_original_reservation(workflow_db):
    from app.models import BusinessInvoice

    try:
        with client_for(workflow_db) as client:
            first = upload(client, workflow_db)
            assert first["outcome"] == "VALIDATED"
            duplicate = upload(
                client, workflow_db, quantity="30", subtotal="600", tax="60", total="660"
            )
            assert duplicate["outcome"] == "NEEDS_REVIEW"
            task = client.get("/api/v1/reviews").json()["tasks"][0]
            result = client.post(
                "/api/v1/reviews/" + task["id"] + "/corrections",
                json={
                    "version": task["version"],
                    "comment": "Confirm vendor identity against original vendor evidence.",
                    "values": {"invoice_number": "SYN-INV-001"},
                },
            )
            assert result.status_code == 202, result.text
            run_once(workflow_db)
            assert (
                client.get("/api/v1/runs/" + result.json()["run_id"]).json()["outcome"]
                == "NEEDS_REVIEW"
            )
            task = client.get("/api/v1/reviews/" + task["id"]).json()
            assert (
                client.post(
                    "/api/v1/reviews/" + task["id"] + "/release",
                    json={
                        "version": task["version"],
                        "comment": "Reject conflicting duplicate without altering the original.",
                    },
                ).status_code
                == 200
            )
            with workflow_db() as session:
                commitment = session.scalar(select(FinancialCommitment))
                assert commitment.status == "RESERVED" and commitment.amount == Decimal("550")
                assert session.scalar(select(BusinessInvoice)).total == Decimal("550")
    finally:
        app.dependency_overrides.clear()


def test_blocked_correction_preserves_canonical_identity(workflow_db):
    from app.models import BusinessInvoice

    try:
        with client_for(workflow_db) as client:
            first = upload(client, workflow_db)
            task = client.post("/api/v1/runs/" + first["id"] + "/review").json()
            response = client.post(
                "/api/v1/reviews/" + task["id"] + "/corrections",
                json={
                    "version": task["version"],
                    "comment": "Check a proposed identity change and unauthorized currency.",
                    "values": {"invoice_number": "PROPOSED-CHANGE", "currency": "EUR"},
                },
            )
            assert response.status_code == 202
            run_once(workflow_db)
            assert (
                client.get("/api/v1/runs/" + response.json()["run_id"]).json()["outcome"]
                == "BLOCKED"
            )
            with workflow_db() as session:
                invoice = session.scalar(select(BusinessInvoice))
                assert invoice.invoice_number == "SYN-INV-001" and invoice.currency == "USD"
                assert session.scalar(select(FinancialCommitment)).status == "HELD"
    finally:
        app.dependency_overrides.clear()
