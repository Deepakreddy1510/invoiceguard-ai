"""Disposable legacy sample fixture; persisted email evidence, no live Gmail/provider calls."""

import json
import time
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.ingestion import ingest
from app.models import EmailAttachment, EmailMessage, GmailConnection, ProcessingRun
from app.worker.main import run_once
from app.workspace_service import provision_sample
from scripts.generate_samples import invoice_pdf


def main():
    settings = get_settings()
    if (
        not (make_url(settings.database_url).database or "").endswith("_e2e")
        or settings.auth_mode != "local"
        or settings.app_environment != "local"
    ):
        raise RuntimeError("Fixture requires a disposable local *_e2e database.")
    factory = sessionmaker(create_engine(settings.database_url))
    wid = uuid4()
    subject = "local-demo-reviewer"
    with factory.begin() as s:
        provision_sample(s, SimpleNamespace(subject=subject), wid, "Previously emailed sample")
    payload = invoice_pdf(number="RETAINED-EMAIL-INVOICE")
    with factory() as s:
        receipt = ingest(
            BytesIO(payload),
            "retained-email.pdf",
            None,
            s,
            wid,
            subject,
            extraction_mode="FALLBACK",
        )
    run_once(factory, run_id=UUID(receipt["run_id"]))
    for _ in range(100):
        with factory() as s:
            if s.get(ProcessingRun, UUID(receipt["run_id"])).status in ["SUCCEEDED", "FAILED"]:
                break
        time.sleep(0.1)
    with factory.begin() as s:
        connection = GmailConnection(
            workspace_id=wid,
            subject=subject,
            email="retained@example.invalid",
            history_id="original-checkpoint",
            credentials=None,
        )
        s.add(connection)
        s.flush()
        message = EmailMessage(
            workspace_id=wid,
            connection_id=connection.id,
            gmail_id="original-message",
            sender="supplier@example.invalid",
            subject="Existing source invoice",
            body="Persisted synthetic email; provider calls are not live.",
        )
        s.add(message)
        s.flush()
        s.add(
            EmailAttachment(
                workspace_id=wid,
                message_id=message.id,
                part_id="1",
                filename="retained-email.pdf",
                mime_type="application/pdf",
                byte_size=len(payload),
                document_id=UUID(receipt["document_id"]),
                run_id=UUID(receipt["run_id"]),
                status="PROCESSED",
            )
        )
    print(json.dumps({"workspace_id": str(wid), **receipt}))


if __name__ == "__main__":
    main()
