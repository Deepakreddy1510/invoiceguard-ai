import csv
from decimal import Decimal
from io import StringIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.extraction.fallback import fallback
from app.extraction.gemini import GeminiUnavailable
from app.main import app
from app.models import (
    BusinessInvoice,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
)
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf
from tests.application import test_security
from tests.application.test_review import client_for, upload

secure_client = test_security.secure_client


def mine(client):
    response = client.post("/api/v1/workspaces/bootstrap")
    assert response.status_code == 200, response.text
    data = response.json()
    workspace = next(w for w in data["workspaces"] if w["kind"] == "MY")
    return {"X-Workspace-ID": workspace["id"]}


def vendor_data(**changes):
    return {
        "legal_name": "Independent Supplier (Synthetic)",
        "code": "OWN-001",
        "tax_id": "SYNTHETIC-OWN-TAX",
        "status": "APPROVED",
        **changes,
    }


def po_data(vendor, **changes):
    return {
        "number": "OWN-PO-001",
        "vendor_id": vendor,
        "currency": "USD",
        "status": "OPEN",
        "issued_on": "2026-01-01",
        "valid_until": "2026-12-31",
        "billing_mode": "ITEMIZED",
        "authorized_gross": "220.00",
        "items": [
            {
                "sku": "PAPER-A4",
                "description": "Synthetic paper",
                "quantity": "10",
                "unit_price": "20",
                "tax_rate": "0.10",
            }
        ],
        **changes,
    }


def process(client, factory, headers=None, mode="AUTO", payload=None, **settings):
    response = client.post(
        "/api/v1/documents",
        headers=headers or {},
        data={"extraction_mode": mode},
        files={"file": ("independent.pdf", payload or invoice_pdf(**settings), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    receipt = response.json()
    run_once(factory, run_id=UUID(receipt["run_id"]))
    return client.get("/api/v1/runs/" + receipt["run_id"], headers=headers or {}).json(), receipt


@pytest.fixture
def product_client(workflow_db):
    try:
        with client_for(workflow_db) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_workspace_bootstrap_is_idempotent_empty_private_and_preserves_demo(
    product_client, workflow_db
):
    client = product_client
    original = upload(client, workflow_db)
    with workflow_db() as session:
        before = [
            (str(c.id), str(c.amount), c.status)
            for c in session.scalars(select(FinancialCommitment))
        ]
    headers = mine(client)
    assert mine(client) == headers
    assert client.get("/api/v1/vendors", headers=headers).json() == []
    assert client.get("/api/v1/purchase-orders", headers=headers).json() == []
    assert client.get("/api/v1/runs", headers=headers).json()["runs"] == []
    assert client.get("/api/v1/dashboard", headers=headers).json()["total_invoices"] == 0
    assert client.get("/api/v1/runs/" + original["id"], headers=headers).status_code == 404
    assert (
        client.get("/api/v1/vendors", headers={"X-Workspace-ID": str(uuid4())}).status_code == 403
    )
    with workflow_db() as session:
        assert before == [
            (str(c.id), str(c.amount), c.status)
            for c in session.scalars(select(FinancialCommitment))
        ]


def test_private_workspaces_require_each_users_membership(secure_client):
    client, factory, token = secure_client
    from app.config import DEMO_WORKSPACE_ID
    from app.models import Membership

    with factory.begin() as session:
        session.add_all(
            [
                Membership(workspace_id=DEMO_WORKSPACE_ID, subject=subject, role="REVIEWER")
                for subject in [
                    "f739bbd3-944a-5c78-b21d-49e0767f45a0",
                    "51c05e63-c5be-5340-b726-4a933cecdee8",
                ]
            ]
        )
    a = {
        **token("f739bbd3-944a-5c78-b21d-49e0767f45a0"),
        **mine_with_token(client, token("f739bbd3-944a-5c78-b21d-49e0767f45a0")),
    }
    b = {
        **token("51c05e63-c5be-5340-b726-4a933cecdee8"),
        **mine_with_token(client, token("51c05e63-c5be-5340-b726-4a933cecdee8")),
    }
    assert a["X-Workspace-ID"] != b["X-Workspace-ID"]
    created = client.post("/api/v1/vendors", headers=a, json=vendor_data())
    assert created.status_code == 201
    assert client.get("/api/v1/vendors", headers=b).json() == []
    assert client.get("/api/v1/vendors/" + created.json()["id"], headers=b).status_code == 404
    assert (
        client.get(
            "/api/v1/vendors",
            headers={
                **token("51c05e63-c5be-5340-b726-4a933cecdee8"),
                "X-Workspace-ID": a["X-Workspace-ID"],
            },
        ).status_code
        == 403
    )
    assert client.get("/api/v1/me", headers=a).json()["can_select_extraction_mode"] is False
    assert (
        client.post(
            "/api/v1/documents",
            headers=a,
            data={"extraction_mode": "FALLBACK"},
            files={"file": ("a.pdf", invoice_pdf(), "application/pdf")},
        ).status_code
        == 403
    )


def mine_with_token(client, headers):
    response = client.post("/api/v1/workspaces/bootstrap", headers=headers)
    assert response.status_code == 200, response.text
    return {
        "X-Workspace-ID": next(w["id"] for w in response.json()["workspaces"] if w["kind"] == "MY")
    }


def test_vendor_identity_versions_and_safe_deletion(product_client):
    client = product_client
    headers = mine(client)
    created = client.post("/api/v1/vendors", headers=headers, json=vendor_data())
    assert created.status_code == 201, created.text
    vendor = created.json()
    assert (
        client.post(
            "/api/v1/vendors", headers=headers, json=vendor_data(code="own-001")
        ).status_code
        == 409
    )
    assert (
        client.post("/api/v1/vendors", headers=headers, json=vendor_data(code="OTHER")).status_code
        == 409
    )
    updated = client.put(
        "/api/v1/vendors/" + vendor["id"],
        headers=headers,
        json={**vendor_data(legal_name="Corrected supplier"), "version": vendor["version"]},
    )
    assert updated.status_code == 200, updated.text
    assert (
        client.put(
            "/api/v1/vendors/" + vendor["id"], headers=headers, json={**vendor_data(), "version": 1}
        ).status_code
        == 409
    )
    vendor = updated.json()
    po = client.post("/api/v1/purchase-orders", headers=headers, json=po_data(vendor["id"]))
    assert po.status_code == 201, po.text
    assert (
        client.put(
            "/api/v1/vendors/" + vendor["id"],
            headers=headers,
            json={**vendor_data(legal_name="Different identity"), "version": vendor["version"]},
        ).status_code
        == 409
    )
    assert (
        client.delete(
            "/api/v1/vendors/" + vendor["id"] + "?version=" + str(vendor["version"]),
            headers=headers,
        ).status_code
        == 409
    )
    deactivated = client.put(
        "/api/v1/vendors/" + vendor["id"],
        headers=headers,
        json={
            **vendor_data(legal_name=vendor["legal_name"], status="INACTIVE"),
            "version": vendor["version"],
        },
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "INACTIVE"
    assert (
        client.delete(
            "/api/v1/purchase-orders/" + po.json()["id"] + "?version=1", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.delete(
            "/api/v1/vendors/" + vendor["id"] + "?version=" + str(deactivated.json()["version"]),
            headers=headers,
        ).status_code
        == 200
    )
    assert "VENDOR_DELETED" in client.get("/api/v1/audit-events", headers=headers).text


@pytest.mark.parametrize(
    "currency,authorization",
    [
        ("USD", "220.00"),
        ("EUR", "220.00"),
        ("INR", "220.00"),
        ("GBP", "220.00"),
        ("JPY", "220"),
        ("KWD", "220.000"),
    ],
)
def test_procurement_currency_rounding(product_client, currency, authorization):
    client = product_client
    headers = mine(client)
    vendor = client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    response = client.post(
        "/api/v1/purchase-orders",
        headers=headers,
        json=po_data(vendor["id"], currency=currency, authorized_gross=authorization),
    )
    assert response.status_code == 201, response.text
    assert client.get("/api/v1/purchase-orders", headers=headers).json()[0][
        "available_gross"
    ] == str(Decimal(authorization).quantize(Decimal(".000001")))


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "AUD"},
        {"authorized_gross": "220.001"},
        {"authorized_gross": 220.0},
        {"valid_until": "2025-12-31"},
        {"items": []},
        {"authorized_gross": "999.00"},
        {"status": "PARTIALLY_BILLED"},
    ],
)
def test_invalid_procurement_rejected_without_partial_records(product_client, changes):
    client = product_client
    headers = mine(client)
    vendor = client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    assert (
        client.post(
            "/api/v1/purchase-orders", headers=headers, json=po_data(vendor["id"], **changes)
        ).status_code
        == 422
    )
    assert client.get("/api/v1/purchase-orders", headers=headers).json() == []


def test_real_custom_procurement_partial_billing_history_and_retention(product_client, workflow_db):
    client = product_client
    headers = mine(client)
    vendor = client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    po = client.post("/api/v1/purchase-orders", headers=headers, json=po_data(vendor["id"])).json()
    common = {
        "vendor_name": vendor["legal_name"],
        "vendor_code": vendor["code"],
        "vendor_tax_id": vendor["tax_id"],
        "po": "OWN-PO-001",
    }
    for number, q, net, tax, total, expected in [
        ("OWN-1", "3", "60", "6", "66", "VALIDATED"),
        ("OWN-2", "5", "100", "10", "110", "VALIDATED"),
        ("OWN-OVER", "4", "80", "8", "88", "BLOCKED"),
    ]:
        detail, _ = process(
            client,
            workflow_db,
            headers,
            number=number,
            quantity=q,
            subtotal=net,
            tax=tax,
            total=total,
            **common,
        )
        assert detail["outcome"] == expected, detail
    duplicate, _ = process(
        client,
        workflow_db,
        headers,
        number="OWN-1",
        quantity="3",
        subtotal="60",
        tax="6",
        total="66",
        alternate=True,
        **common,
    )
    assert duplicate["outcome"] == "BLOCKED"
    missing, _ = process(
        client,
        workflow_db,
        headers,
        number="UNNUMBERED",
        quantity="1",
        subtotal="20",
        tax="2",
        total="22",
        missing=True,
        **common,
    )
    assert missing["outcome"] == "NEEDS_REVIEW"
    scan, receipt = process(
        client,
        workflow_db,
        headers,
        number="OWN-SCAN",
        quantity="1",
        subtotal="20",
        tax="2",
        total="22",
        scanned=True,
        **common,
    )
    assert scan["outcome"] == "VALIDATED"
    assert any(
        event["stage"] == "ocr" and event["outcome"] == "SUCCEEDED" for event in scan["events"]
    )
    detail = client.get("/api/v1/purchase-orders/" + po["id"], headers=headers).json()
    assert Decimal(detail["reserved"]) == 198 and Decimal(detail["available"]) == 22
    assert (
        client.put(
            "/api/v1/purchase-orders/" + po["id"],
            headers=headers,
            json={**po_data(vendor["id"]), "version": 1},
        ).status_code
        == 409
    )
    assert (
        client.delete(
            "/api/v1/purchase-orders/" + po["id"] + "?version=1", headers=headers
        ).status_code
        == 409
    )
    assert (
        client.delete("/api/v1/documents/" + receipt["document_id"], headers=headers).status_code
        == 409
    )
    assert len(client.get("/api/v1/runs?search=OWN-PO-001", headers=headers).json()["runs"]) == 6
    assert client.get("/api/v1/runs?search=%25", headers=headers).status_code == 200
    cancelled = client.post(
        "/api/v1/purchase-orders/" + po["id"] + "/cancel",
        headers=headers,
        json={
            "version": 1,
            "reason": "Authorization cancelled for future invoices; existing history retained.",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert (
        Decimal(
            client.get("/api/v1/purchase-orders/" + po["id"], headers=headers).json()["reserved"]
        )
        == 198
    )


def test_amount_based_edit_and_cross_workspace_vendor_denied(product_client):
    client = product_client
    headers = mine(client)
    legacy = client.get("/api/v1/vendors").json()[0]
    assert (
        client.post(
            "/api/v1/purchase-orders", headers=headers, json=po_data(legacy["id"])
        ).status_code
        == 404
    )
    vendor = client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    data = po_data(vendor["id"], billing_mode="AMOUNT_BASED", items=[], authorized_gross="1000.00")
    created = client.post("/api/v1/purchase-orders", headers=headers, json=data)
    assert created.status_code == 201
    changed = client.put(
        "/api/v1/purchase-orders/" + created.json()["id"],
        headers=headers,
        json={**data, "authorized_gross": "1500.00", "version": 1},
    )
    assert changed.status_code == 200, changed.text
    assert (
        client.put(
            "/api/v1/purchase-orders/" + created.json()["id"],
            headers=headers,
            json={**data, "version": 1},
        ).status_code
        == 409
    )


def csv_bytes(rows):
    out = StringIO()
    writer = csv.writer(out)
    writer.writerows(rows)
    return out.getvalue().encode()


def test_csv_preview_atomic_commit_replay_and_formula_rejection(product_client):
    client = product_client
    headers = mine(client)
    template = client.get(
        "/api/v1/procurement/imports/templates/vendors.csv", headers=headers
    ).content
    invalid = template + b"Conflicting supplier,MY-V001,DIFFERENT-TAX,APPROVED\r\n"

    def post(kind, action, payload, key="csv-key"):
        return client.post(
            "/api/v1/procurement/imports/" + action + "?kind=" + kind,
            headers={**headers, "Idempotency-Key": key},
            files={"file": ("import.csv", payload, "text/csv")},
        )

    preview = post("vendors", "preview", invalid)
    assert (
        preview.status_code == 200
        and not preview.json()["valid"]
        and preview.json()["errors"][0]["row"] == 3
    )
    assert post("vendors", "commit", invalid).status_code == 422
    assert client.get("/api/v1/vendors", headers=headers).json() == []
    assert post("vendors", "preview", template).json()["valid"]
    first = post("vendors", "commit", template)
    assert first.status_code == 200, first.text
    assert post("vendors", "commit", template).json()["replayed"]
    po_csv = client.get(
        "/api/v1/procurement/imports/templates/purchase-orders.csv", headers=headers
    ).content
    bad_po = po_csv.replace(b"1000.00", b"not-a-decimal")
    assert post("purchase-orders", "commit", bad_po, "bad-po").status_code == 422
    assert client.get("/api/v1/purchase-orders", headers=headers).json() == []
    assert post("purchase-orders", "preview", po_csv).json()["valid"]
    assert post("purchase-orders", "commit", po_csv, "good-po").json()["record_count"] == 2
    assert len(client.get("/api/v1/purchase-orders", headers=headers).json()) == 2
    formula = csv_bytes(
        [
            ["legal_name", "code", "tax_id", "status"],
            ["=EXECUTE()", "FORMULA", "TAX-FORMULA", "APPROVED"],
        ]
    )
    assert post("vendors", "preview", formula).status_code == 422


def test_forced_fallback_never_calls_gemini(product_client, workflow_db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-contract-key")
    get_settings.cache_clear()

    def forbidden(*args):
        raise AssertionError("Fallback must not call Gemini")

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", forbidden)
    detail, _ = process(product_client, workflow_db, mode="FALLBACK")
    assert detail["status"] == "SUCCEEDED" and detail["outcome"] == "VALIDATED"
    assert (
        detail["requested_mode"] == "FALLBACK"
        and detail["actual_provider"] == "FALLBACK"
        and detail["model"] is None
    )


def test_auto_provider_failure_is_safe_fallback(product_client, workflow_db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-contract-key")
    get_settings.cache_clear()

    def unavailable(*args):
        raise GeminiUnavailable("sensitive-provider-body")

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", unavailable)
    detail, _ = process(product_client, workflow_db)
    assert (
        detail["requested_mode"] == "AUTO"
        and detail["actual_provider"] == "FALLBACK"
        and detail["outcome"] == "VALIDATED"
    )
    assert detail["fallback_reason"] and "sensitive-provider-body" not in str(detail)


@pytest.mark.parametrize("failure", [False, True, "verification"])
def test_gemini_comparison_retains_history_and_one_consuming_commitment(
    product_client, workflow_db, monkeypatch, failure
):
    client = product_client
    payload = invoice_pdf(number="COMPARE-MODES")
    original, _ = process(client, workflow_db, mode="FALLBACK", payload=payload)
    assert original["outcome"] == "VALIDATED"
    assert (
        client.post(
            "/api/v1/documents",
            data={"extraction_mode": "GEMINI"},
            files={"file": ("a.pdf", payload, "application/pdf")},
        ).status_code
        == 422
    )
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-contract-key")
    get_settings.cache_clear()
    calls = []

    def adapter(pages, key, model):
        calls.append(model)
        if failure is True:
            raise GeminiUnavailable("sensitive-provider-body")
        result = fallback(pages)
        if failure == "verification":
            result.total.value = "9999"
        return result

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", adapter)
    response = client.post(
        "/api/v1/documents",
        data={"extraction_mode": "GEMINI"},
        files={"file": ("a.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    assert response.json()["run_id"] != original["id"]
    with workflow_db() as session:
        assert session.scalar(select(FinancialCommitment.status)) == "HELD"
    run_once(workflow_db, run_id=UUID(response.json()["run_id"]))
    detail = client.get("/api/v1/runs/" + response.json()["run_id"]).json()
    assert calls and detail["requested_mode"] == "GEMINI"
    assert client.get("/api/v1/runs/" + original["id"]).json()["outcome"] == "VALIDATED"
    with workflow_db() as session:
        consuming = session.scalars(
            select(FinancialCommitment).where(
                FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"])
            )
        ).all()
        assert len(consuming) == 1 and consuming[0].amount == 550
        assert session.scalar(select(func.count()).select_from(BusinessInvoice)) == 1
        assert session.scalar(select(func.count()).select_from(Decision)) == (1 if failure else 2)
    if failure:
        assert (
            detail["status"] == "FAILED"
            and detail["actual_provider"] == "NONE"
            and detail["decision"] is None
        )
        assert detail["extraction"][
            "attempted_provider"
        ] == "GEMINI" and "sensitive-provider-body" not in str(detail)
    else:
        assert (
            detail["outcome"] == "VALIDATED"
            and detail["actual_provider"] == "GEMINI"
            and detail["model"]
        )


def test_fresh_demo_is_scoped_add_only_and_queues_real_runs(product_client, workflow_db):
    client = product_client
    original = upload(client, workflow_db)
    headers = mine(client)
    request_id = str(uuid4())
    result = client.post(
        "/api/v1/workspaces/fresh-demo",
        headers=headers,
        json={"request_id": request_id, "confirm_create": True},
    )
    assert result.status_code == 201, result.text
    fresh_headers = {"X-Workspace-ID": result.json()["workspace_id"]}
    assert len(client.get("/api/v1/vendors", headers=fresh_headers).json()) == 18
    assert len(client.get("/api/v1/purchase-orders", headers=fresh_headers).json()) == 36
    assert len(client.get("/api/v1/runs", headers=fresh_headers).json()["runs"]) == 16
    repeated = client.post(
        "/api/v1/workspaces/fresh-demo",
        headers=headers,
        json={"request_id": request_id, "confirm_create": True},
    )
    assert repeated.status_code == 201 and repeated.json()["replayed"]
    assert len(client.get("/api/v1/runs", headers=fresh_headers).json()["runs"]) == 16
    with workflow_db() as session:
        runs = session.scalars(
            select(ProcessingRun)
            .join(InvoiceDocument)
            .where(InvoiceDocument.workspace_id == UUID(fresh_headers["X-Workspace-ID"]))
            .order_by(ProcessingRun.created_at)
        ).all()
        identifiers = [r.id for r in runs]
    for identifier in identifiers:
        run_once(workflow_db, run_id=identifier)
    outcomes = {
        r["outcome"] for r in client.get("/api/v1/runs", headers=fresh_headers).json()["runs"]
    }
    assert {"VALIDATED", "NEEDS_REVIEW", "BLOCKED"} <= outcomes
    assert client.get("/api/v1/runs/" + original["id"]).json()["outcome"] == "VALIDATED"
    with workflow_db() as session:
        assert (
            session.scalar(
                select(FinancialCommitment.amount)
                .join(BusinessInvoice)
                .where(BusinessInvoice.source_document_id == UUID(original["document_id"]))
            )
            == 550
        )


def test_concurrent_duplicate_creation_is_serialized(product_client):
    from concurrent.futures import ThreadPoolExecutor

    headers = mine(product_client)

    def submit(_):
        return product_client.post(
            "/api/v1/vendors", headers=headers, json=vendor_data()
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [201, 409]
    assert len(product_client.get("/api/v1/vendors", headers=headers).json()) == 1


def test_viewer_cannot_mutate_procurement_or_import_shared_demo(secure_client):
    from app.config import DEMO_WORKSPACE_ID
    from app.models import Membership

    client, factory, token = secure_client
    with factory.begin() as session:
        session.add(
            Membership(
                workspace_id=DEMO_WORKSPACE_ID,
                subject="d5b4404e-0ce1-5078-a73f-546f61f496cc",
                role="VIEWER",
            )
        )
    assert client.post("/api/v1/vendors", json=vendor_data()).status_code == 401
    assert client.post("/api/v1/vendors", headers=token(), json=vendor_data()).status_code == 403
    assert (
        client.post(
            "/api/v1/purchase-orders", headers=token(), json=po_data(str(uuid4()))
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/procurement/imports/templates/vendors.csv", headers=token()).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/workspaces/fresh-demo",
            headers=token(),
            json={"request_id": str(uuid4()), "confirm_create": True},
        ).status_code
        == 403
    )


def test_existing_database_decimal_precision_can_be_edited(product_client):
    headers = mine(product_client)
    vendor = product_client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    data = po_data(vendor["id"])
    data["items"][0].update(quantity="10.000000", unit_price="20.000000", tax_rate="0.10000000")
    response = product_client.post("/api/v1/purchase-orders", headers=headers, json=data)
    assert response.status_code == 201, response.text
    assert (
        product_client.put(
            "/api/v1/purchase-orders/" + response.json()["id"],
            headers=headers,
            json={**data, "version": 1},
        ).status_code
        == 200
    )


def test_deleting_settled_invoice_never_releases_settlement(product_client, workflow_db):
    run, receipt = process(product_client, workflow_db)
    with workflow_db.begin() as session:
        commitment = session.scalar(select(FinancialCommitment))
        commitment.status = "SETTLED"
        identifier = commitment.id
    assert product_client.delete("/api/v1/documents/" + receipt["document_id"]).status_code == 409
    with workflow_db() as session:
        assert session.get(FinancialCommitment, identifier).status == "SETTLED"
        assert session.scalar(select(func.count()).select_from(Decision)) == 1


def test_matched_vendor_is_retained_even_without_canonical_invoice(product_client, workflow_db):
    headers = mine(product_client)
    vendor = product_client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    run, _ = process(
        product_client,
        workflow_db,
        headers=headers,
        vendor_name=vendor["legal_name"],
        vendor_code=vendor["code"],
        vendor_tax_id=vendor["tax_id"],
        po="ABSENT-PO",
        missing=True,
    )
    assert run["decision"]["summary"]["vendor"] == vendor["legal_name"]
    with workflow_db() as session:
        assert session.scalar(select(func.count()).select_from(BusinessInvoice)) == 0
    view = product_client.get("/api/v1/vendors/" + vendor["id"], headers=headers).json()
    assert view["identity_locked"] is True
    assert (
        product_client.delete(
            "/api/v1/vendors/" + vendor["id"] + "?version=1", headers=headers
        ).status_code
        == 409
    )
    assert (
        product_client.put(
            "/api/v1/vendors/" + vendor["id"],
            headers=headers,
            json=vendor_data(legal_name="Changed Identity", version=1),
        ).status_code
        == 409
    )
