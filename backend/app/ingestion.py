import hashlib
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.audit import audit, financial_lock
from app.config import DEMO_WORKSPACE_ID, get_settings
from app.extraction.pdf import PDFError, pdf_process
from app.models import (
    BusinessInvoice,
    DocumentSubmission,
    InvoiceDocument,
    ProcessingRun,
    RunEvent,
)
from app.storage import persist_document, remove_document


def ingest(
    stream,
    filename: str,
    key: str | None,
    session,
    workspace_id=DEMO_WORKSPACE_ID,
    actor="local-demo-reviewer",
    extraction_mode="AUTO",
    email_attachment_id=None,
    intake_context=None,
) -> dict:
    if extraction_mode not in ["AUTO", "GEMINI", "FALLBACK"]:
        raise HTTPException(422, "Unsupported extraction mode.")
    settings = get_settings()
    storage = settings.storage_dir.resolve()
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    doc_id = uuid4()
    path = storage / f"{doc_id}.pdf"
    digest = hashlib.sha256()
    size = 0
    committing = False
    storage_attempted = False
    with tempfile.NamedTemporaryFile(dir=storage, delete=False) as target:
        temporary = Path(target.name)
        try:
            while chunk := stream.read(64 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "PDF exceeds 10 MiB upload limit.")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            target.close()
            with temporary.open("rb") as signature:
                is_pdf = signature.read(5) == b"%PDF-"
            if size == 0 or not is_pdf:
                raise HTTPException(422, "A real PDF signature is required.")
            try:
                metadata = pdf_process(temporary, False)
            except PDFError as exc:
                raise HTTPException(422, str(exc)) from exc
            sha = digest.hexdigest()
            if key:
                # Same key is serialized even when submissions contain different bytes.
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"{workspace_id}:{key}"},
                )
                previous = session.scalar(
                    select(DocumentSubmission).where(
                        DocumentSubmission.workspace_id == workspace_id,
                        DocumentSubmission.idempotency_key == key,
                    )
                )
                if previous:
                    document = session.get(InvoiceDocument, previous.document_id)
                    if document.sha256 != sha or previous.requested_mode != extraction_mode:
                        raise HTTPException(
                            409,
                            "Idempotency key already used for different PDF bytes or extraction mode.",
                        )
                    return {
                        "run_id": str(previous.run_id),
                        "document_id": str(document.id),
                        "replayed": True,
                    }
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"invoiceguard-document:{workspace_id}:{sha}"},
            )
            os.replace(temporary, path)
            inserted = session.scalar(
                insert(InvoiceDocument)
                .values(
                    id=doc_id,
                    workspace_id=workspace_id,
                    sha256=sha,
                    storage_key=path.name,
                    byte_size=size,
                    page_count=metadata["page_count"],
                )
                .on_conflict_do_nothing(index_elements=["workspace_id", "sha256"])
                .returning(InvoiceDocument.id)
            )
            replayed = inserted is None
            if replayed:
                path.unlink(missing_ok=True)
                document = session.scalar(
                    select(InvoiceDocument).where(
                        InvoiceDocument.workspace_id == workspace_id,
                        InvoiceDocument.sha256 == sha,
                    )
                )
                run = session.scalar(
                    select(ProcessingRun)
                    .where(ProcessingRun.document_id == document.id)
                    .order_by(ProcessingRun.created_at.desc())
                    .limit(1)
                )
                if run.extraction_mode != extraction_mode:
                    if run.status not in ["SUCCEEDED", "FAILED"]:
                        raise HTTPException(
                            409,
                            "Wait for this document's active run before changing extraction mode.",
                        )
                    financial_lock(session, workspace_id)
                    parent = run
                    run = ProcessingRun(
                        intake_context=intake_context or parent.intake_context,
                        document_id=document.id,
                        parent_run_id=parent.id,
                        extraction_mode=extraction_mode,
                    )
                    session.add(run)
                    session.flush()
                    from app.review.service import ensure_task, hold

                    original = session.scalar(
                        select(BusinessInvoice).where(
                            BusinessInvoice.workspace_id == workspace_id,
                            BusinessInvoice.source_document_id == document.id,
                        )
                    )
                    task = ensure_task(session, run, original.id if original else None)
                    task.status = "REVALIDATING"
                    hold(
                        session,
                        original.id if original else None,
                        workspace_id,
                        actor,
                        document.id,
                        run.id,
                    )
                    session.add(
                        RunEvent(
                            run_id=run.id,
                            attempt=0,
                            stage="reextraction",
                            outcome="QUEUED",
                            detail="Explicit extraction-mode comparison queued; prior decisions and consuming capacity are preserved.",
                        )
                    )
                    replayed = False
            else:
                document = session.get(InvoiceDocument, doc_id)
                storage_attempted = True
                persist_document(path, path.name)
                run = ProcessingRun(
                    document_id=doc_id,
                    extraction_mode=extraction_mode,
                    intake_context=intake_context,
                )
                session.add(run)
                session.flush()
                session.add(
                    RunEvent(
                        run_id=run.id,
                        attempt=0,
                        stage="ingestion",
                        outcome="SUCCEEDED",
                        detail=f"PDF verified: {metadata['page_count']} page(s), {size} bytes.",
                    )
                )
            session.add(
                DocumentSubmission(
                    workspace_id=workspace_id,
                    document_id=document.id,
                    run_id=run.id,
                    idempotency_key=key,
                    original_filename=Path(filename).name[:255],
                    requested_mode=extraction_mode,
                )
            )
            audit(
                session,
                workspace_id,
                actor,
                "DOCUMENT_REPLAYED" if replayed else "DOCUMENT_ACCEPTED",
                {
                    "sha256": sha,
                    "filename": Path(filename).name[:255],
                    "requested_mode": extraction_mode,
                },
                document.id,
                run.id,
            )
            response = {
                "run_id": str(run.id),
                "document_id": str(document.id),
                "replayed": replayed,
            }
            if email_attachment_id:
                from app.models import EmailAttachment

                attachment = session.get(EmailAttachment, email_attachment_id)
                if not attachment or attachment.workspace_id != workspace_id:
                    raise HTTPException(404, "Email intake record not found in this workspace.")
                attachment.document_id = document.id
                attachment.run_id = run.id
                attachment.sha256 = sha
                attachment.replayed = replayed
                attachment.status = "INGESTED"
                attachment.error = None
            committing = True
            session.commit()
            return response
        except Exception:
            session.rollback()
            # A failed commit acknowledgement can be ambiguous. Retain the immutable
            # artifact rather than risk deleting a document whose metadata committed.
            if not committing:
                path.unlink(missing_ok=True)
                if storage_attempted:
                    try:
                        remove_document(path.name)
                    except Exception:
                        pass
            raise
        finally:
            temporary.unlink(missing_ok=True)
            if settings.storage_backend == "s3":
                # S3 is authoritative, even when commit acknowledgement is ambiguous.
                path.unlink(missing_ok=True)
