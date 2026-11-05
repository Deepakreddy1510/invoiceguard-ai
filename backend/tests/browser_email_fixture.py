"""Provider-mocked Gmail browser contract fixture; never part of the runtime image.

Run only against an explicitly disposable database. No Gmail/Gemini network calls.
"""

import json
import os
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth import Access
from app.config import get_settings
from app.email_intake import google
from app.email_intake.service import intake_attachment, sync_connection
from app.models import EmailAttachment, EmailMessage, GmailConnection, Workspace
from app.procurement import POInput, VendorInput, create_po, create_vendor
from scripts.dataset_v2.isolation import validate_name
from scripts.generate_samples import invoice_pdf
from tests.application.test_gmail import b64, raw_message


def main(stage):
    settings = get_settings()
    database = make_url(settings.database_url).database or ""
    if not database.endswith(("_test", "_e2e")):
        validate_name(database)
    if (
        settings.app_environment != "local"
        or settings.auth_mode != "local"
        or settings.storage_backend != "local"
    ):
        raise RuntimeError("Browser fixture requires isolated local runtime.")
    for name, value in {
        "GMAIL_CLIENT_ID": "provider-contract-only",
        "GMAIL_CLIENT_SECRET": "provider-contract-only",
        "GMAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "GMAIL_USE_GEMINI": "false",
    }.items():
        os.environ[name] = value
    get_settings.cache_clear()
    engine = create_engine(settings.database_url)
    factory = sessionmaker(engine)
    workspace_id = uuid5(NAMESPACE_URL, "invoiceguard:gmail-browser-contract")
    with factory.begin() as s:
        w = s.get(Workspace, workspace_id)
        if stage == "initial":
            if w:
                raise RuntimeError(
                    "This disposable browser fixture already exists; never reset existing records."
                )
            s.add(
                Workspace(
                    id=workspace_id,
                    name="Email contract workspace",
                    kind="CUSTOM",
                    owner_subject="local-demo-reviewer",
                )
            )
            s.flush()
            user = Access("local-demo-reviewer", workspace_id, "ADMIN")
            vendor = create_vendor(
                s,
                user,
                VendorInput(
                    legal_name="Gmail Browser Supplier (Synthetic)",
                    code="GMAIL-BROWSER",
                    tax_id="SYNTHETIC-GMAIL-BROWSER",
                ),
            )
            create_po(
                s,
                user,
                POInput(
                    number="GMAIL-BROWSER-PO",
                    vendor_id=vendor.id,
                    currency="USD",
                    status="OPEN",
                    issued_on="2026-01-01",
                    valid_until="2026-12-31",
                    billing_mode="ITEMIZED",
                    authorized_gross="220",
                    items=[
                        {
                            "sku": "PAPER-A4",
                            "description": "Synthetic cartons",
                            "quantity": "10",
                            "unit_price": "20",
                            "tax_rate": "0.10",
                        }
                    ],
                ),
            )
            c = GmailConnection(
                workspace_id=workspace_id,
                subject="local-demo-reviewer",
                email="provider-contract@example.invalid",
                history_id="100",
                status="ACTIVE",
                connected_at=google.now(),
            )
            s.add(c)
        else:
            if not w:
                raise RuntimeError("Initial browser fixture required.")
            c = s.scalar(
                select(GmailConnection).where(GmailConnection.workspace_id == workspace_id)
            )
        c.credentials = google.seal(
            workspace_id,
            {
                "refresh_token": "provider-contract",
                "access_token": "provider-contract",
                "expires_at": google.now().timestamp() + 3600,
            },
        )
        c.next_sync_at = google.now() - timedelta(seconds=1)
        s.flush()
        connection_id = c.id
    qty, net, tax, total = (
        ("3", "60", "6", "66") if stage == "initial" else ("8", "160", "16", "176")
    )
    pdf = invoice_pdf(
        number="EMAIL-BROWSER-" + stage.upper(),
        vendor_name="Gmail Browser Supplier (Synthetic)",
        vendor_code="GMAIL-BROWSER",
        vendor_tax_id="SYNTHETIC-GMAIL-BROWSER",
        po="GMAIL-BROWSER-PO",
        quantity=qty,
        subtotal=net,
        tax=tax,
        total=total,
    )
    identifier = "browser-" + stage
    raw = raw_message(
        identifier=identifier,
        subject="Provider-mocked Gmail " + stage,
        body="PROVIDER MOCK CONTRACT: no live Gmail message received. PO: GMAIL-BROWSER-PO",
        files=[("contract-" + stage + ".pdf", "application/pdf", pdf)],
    )

    def handler(request):
        if request.url.path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "historyId": "101",
                    "history": [{"messagesAdded": [{"message": {"id": identifier}}]}],
                },
            )
        if "/attachments/" in request.url.path:
            return httpx.Response(200, json={"data": b64(pdf)})
        if request.url.path.endswith("/" + identifier):
            return httpx.Response(200, json=raw)
        raise AssertionError("Unexpected provider request; live network is forbidden.")

    class ProviderContract(google.GmailClient):
        def __init__(self, access_token=None, client=None):
            super().__init__(access_token, httpx.Client(transport=httpx.MockTransport(handler)))
            self.owned = True

    google.GmailClient = ProviderContract
    sync_connection(factory, connection_id)
    with factory() as s:
        message_id = s.scalar(
            select(EmailMessage.id).where(
                EmailMessage.gmail_id == identifier, EmailMessage.workspace_id == workspace_id
            )
        )
        attachment_id = s.scalar(
            select(EmailAttachment.id).where(EmailAttachment.message_id == message_id)
        )
    assert attachment_id and intake_attachment(factory, attachment_id)
    with factory() as s:
        attachment = s.get(EmailAttachment, attachment_id)
        assert attachment.run_id, "Provider-mocked PDF did not enter the actual pipeline"
        print(
            json.dumps(
                {
                    "workspace_id": str(workspace_id),
                    "message_id": str(message_id),
                    "run_id": str(attachment.run_id),
                    "provider": "MOCKED_GMAIL_TRANSPORT",
                }
            )
        )
    engine.dispose()


if __name__ == "__main__":
    main(sys.argv[1])
