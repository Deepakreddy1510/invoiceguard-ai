"""Queue visibility is independent of immutable evidence and financial capacity."""

from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.ingestion import ingest
from app.models import (
    EmailAttachment,
    EmailMessage,
    GmailConnection,
    InvoiceDocument,
    Membership,
    SampleInstallation,
)
from app.worker.main import run_once
from app.workspace_service import provision_sample
from scripts.generate_samples import invoice_pdf
from tests.application import test_security
from tests.application.test_customer_auth import CUSTOMER_A, CUSTOMER_B, bootstrap
from tests.application.test_product import po_data, process, vendor_data
from tests.application.test_sample_initialization import drain

secure_client = test_security.secure_client


def test_archive_keeps_pdf_ledger_duplicate_detection_and_authorization(secure_client):
    client, factory, token = secure_client
    wid = bootstrap(client, token, CUSTOMER_A)["default_workspace_id"]
    bootstrap(client, token, CUSTOMER_B)
    headers = {**token(CUSTOMER_A), "X-Workspace-ID": wid}
    vendor = client.post("/api/v1/vendors", headers=headers, json=vendor_data()).json()
    assert (
        client.post(
            "/api/v1/purchase-orders", headers=headers, json=po_data(vendor["id"])
        ).status_code
        == 201
    )
    settings = dict(
        number="ARCHIVE-ONE",
        vendor_name=vendor_data()["legal_name"],
        vendor_code="OWN-001",
        vendor_tax_id="SYNTHETIC-OWN-TAX",
        po="OWN-PO-001",
        quantity="3",
        subtotal="60",
        tax="6",
        total="66",
    )
    run, receipt = process(client, factory, headers=headers, **settings)
    assert run["outcome"] == "VALIDATED"
    doc = receipt["document_id"]
    url = "/api/v1/documents/" + doc
    pdf = client.get(url + "/content", headers=headers).content

    def ledger():
        with factory() as s:
            return {
                table: s.execute(text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY id'))
                .scalars()
                .all()
                for table in [
                    "decisions",
                    "financial_commitments",
                    "invoice_revisions",
                    "invoices",
                    "run_events",
                    "purchase_orders",
                ]
            }

    original = ledger()
    assert (
        client.post(
            url + "/visibility",
            headers={**token(CUSTOMER_B), "X-Workspace-ID": wid},
            json={"archived": True},
        ).status_code
        == 403
    )
    assert (
        client.post(
            url + "/visibility", headers=token(CUSTOMER_B), json={"archived": True}
        ).status_code
        == 404
    )
    for _ in range(2):
        assert (
            client.post(url + "/visibility", headers=headers, json={"archived": True}).status_code
            == 200
        )
    assert client.get("/api/v1/runs", headers=headers).json()["runs"] == []
    assert len(client.get("/api/v1/runs?visibility=archived", headers=headers).json()["runs"]) == 1
    assert len(client.get("/api/v1/runs?visibility=all", headers=headers).json()["runs"]) == 1
    assert client.get("/api/v1/runs/" + run["id"], headers=headers).json()["archived_at"]
    assert client.get(url + "/content", headers=headers).content == pdf
    assert ledger() == original
    assert client.delete(url, headers=headers).status_code == 409
    assert (
        client.post(url + "/visibility", headers=headers, json={"archived": False}).status_code
        == 200
    )
    assert len(client.get("/api/v1/runs", headers=headers).json()["runs"]) == 1
    assert ledger() == original
    assert (
        client.post(url + "/visibility", headers=headers, json={"archived": True}).status_code
        == 200
    )
    duplicate, _ = process(client, factory, headers=headers, alternate=True, **settings)
    assert duplicate["outcome"] == "BLOCKED"
    orders = client.get("/api/v1/purchase-orders", headers=headers).json()
    assert Decimal(orders[0]["reserved_gross"]) == Decimal("66")
    with factory.begin() as s:
        s.scalar(select(Membership).where(Membership.workspace_id == UUID(wid))).role = "VIEWER"
    assert (
        client.post(url + "/visibility", headers=headers, json={"archived": False}).status_code
        == 403
    )


def test_emailed_sample_history_cannot_be_archived_away_and_fresh_sample_is_safe(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    with factory.begin() as s:
        old = provision_sample(s, SimpleNamespace(subject=CUSTOMER_A))
        wid = old.id
    with factory() as s:
        receipt = ingest(
            BytesIO(invoice_pdf(number="EXISTING-EMAIL")),
            "emailed.pdf",
            None,
            s,
            wid,
            CUSTOMER_A,
            extraction_mode="FALLBACK",
        )
    assert run_once(factory, run_id=UUID(receipt["run_id"]))
    with factory.begin() as s:
        connection = GmailConnection(
            workspace_id=wid,
            subject=CUSTOMER_A,
            email="retained@example.invalid",
            history_id="preserve",
            credentials=None,
        )
        s.add(connection)
        s.flush()
        message = EmailMessage(
            workspace_id=wid,
            connection_id=connection.id,
            gmail_id="kept",
            sender="supplier@example.invalid",
            subject="Retained invoice",
            body="Original source email",
        )
        s.add(message)
        s.flush()
        s.add(
            EmailAttachment(
                workspace_id=wid,
                message_id=message.id,
                part_id="1",
                filename="emailed.pdf",
                mime_type="application/pdf",
                byte_size=100,
                document_id=UUID(receipt["document_id"]),
                run_id=UUID(receipt["run_id"]),
                status="PROCESSED",
            )
        )
    headers = {**token(CUSTOMER_A), "X-Workspace-ID": str(wid)}
    assert (
        client.post(
            "/api/v1/documents/" + receipt["document_id"] + "/visibility",
            headers=headers,
            json={"archived": True},
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/workspaces/sample-initialization/start", headers=headers).status_code
        == 409
    )
    response = client.post("/api/v1/workspaces/sample", headers=headers)
    assert response.status_code == 409 and "history" in response.text
    result = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "name": "Clean sample after email",
            "workspace_type": "SAMPLE",
        },
    )
    assert result.status_code == 201, result.text
    fresh = UUID(result.json()["workspace_id"])
    assert fresh != wid
    drain(factory, fresh)
    with factory() as s:
        assert s.get(SampleInstallation, fresh).completed == 21
        assert s.get(InvoiceDocument, UUID(receipt["document_id"]))
        assert (
            s.scalar(select(GmailConnection.history_id).where(GmailConnection.workspace_id == wid))
            == "preserve"
        )
        assert (
            s.scalar(select(EmailMessage.body).where(EmailMessage.workspace_id == wid))
            == "Original source email"
        )
        assert not s.scalar(select(GmailConnection.id).where(GmailConnection.workspace_id == fresh))


def test_gmail_ai_setting_is_read_only_and_distinguishes_missing_provider(
    secure_client, monkeypatch
):
    from app.config import get_settings

    client, _, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    monkeypatch.setenv("GMAIL_USE_GEMINI", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    result = client.get("/api/v1/email", headers=token(CUSTOMER_A)).json()
    assert result["gmail_ai_requested"] is True
    assert result["gmail_ai_available"] is False
    assert result["email_classifier"] == "FALLBACK"
