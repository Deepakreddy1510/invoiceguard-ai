from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import DEMO_WORKSPACE_ID
from app.models import Decision, FinancialCommitment, Vendor
from tests.application.test_review import client_for, upload


@pytest.mark.parametrize("status", ["APPROVED", "SUSPENDED", "INACTIVE"])
def test_shared_name_cannot_override_strong_vendor_identity(workflow_db, status):
    from app.main import app

    factory = workflow_db
    with factory.begin() as session:
        original = session.scalar(select(Vendor).where(Vendor.code == "SYN-001"))
        original.status = status
        session.add(
            Vendor(
                id=uuid4(),
                workspace_id=DEMO_WORKSPACE_ID,
                code="OTHER-IDENTITY",
                legal_name=original.legal_name,
                tax_id="OTHER-TAX",
                status="APPROVED",
            )
        )
    try:
        with client_for(factory) as client:
            result = upload(client, factory)
            assert result["outcome"] == ("VALIDATED" if status == "APPROVED" else "BLOCKED")
            assert (
                next(r for r in result["decision"]["rules"] if r["rule_id"] == "VENDOR_IDENTITY")[
                    "outcome"
                ]
                == "PASS"
            )
            if status != "APPROVED":
                assert (
                    next(
                        r for r in result["decision"]["rules"] if r["rule_id"] == "VENDOR_APPROVED"
                    )["outcome"]
                    == "BLOCK"
                )
    finally:
        app.dependency_overrides.clear()


def test_contradictory_strong_identifiers_are_reviewed(workflow_db):
    from app.main import app

    try:
        with client_for(workflow_db) as client:
            result = upload(client, workflow_db, vendor_tax_id="SYNTHETIC-TAX-2")
            assert result["outcome"] == "NEEDS_REVIEW"
            with workflow_db() as session:
                assert session.scalar(select(FinancialCommitment)) is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("table", ["audit_events", "decisions", "invoice_revisions"])
def test_committed_history_cannot_be_changed(workflow_db, table):
    from app.main import app

    try:
        with client_for(workflow_db) as client:
            upload(client, workflow_db)
        with pytest.raises(DBAPIError, match="immutable"):
            with workflow_db.begin() as session:
                session.execute(text(f"DELETE FROM {table}"))
        with workflow_db() as session:
            assert session.scalar(select(Decision)) is not None
    finally:
        app.dependency_overrides.clear()


def test_corrupt_stored_pdf_fails_without_decision(workflow_db):
    from app.config import get_settings
    from app.main import app
    from app.models import InvoiceDocument
    from app.worker.main import run_once
    from scripts.generate_samples import invoice_pdf

    try:
        with client_for(workflow_db) as client:
            result = client.post(
                "/api/v1/documents",
                files={"file": ("integrity.pdf", invoice_pdf(), "application/pdf")},
            ).json()
            with workflow_db() as session:
                document = session.scalar(select(InvoiceDocument))
                path = get_settings().storage_dir / document.storage_key
            path.write_bytes(invoice_pdf(number="TAMPERED"))
            run_once(workflow_db)
            detail = client.get("/api/v1/runs/" + result["run_id"]).json()
            assert detail["status"] == "FAILED" and detail["decision"] is None
            with workflow_db() as session:
                assert session.scalar(select(FinancialCommitment)) is None
    finally:
        app.dependency_overrides.clear()
