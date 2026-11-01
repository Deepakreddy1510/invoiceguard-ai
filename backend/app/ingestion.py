import hashlib
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.audit import audit
from app.config import DEMO_WORKSPACE_ID, get_settings
from app.extraction.pdf import PDFError, pdf_process
from app.models import DocumentSubmission, InvoiceDocument, ProcessingRun, RunEvent
from app.storage import persist_document, remove_document


def ingest(
    stream,
    filename: str,
    key: str | None,
    session,
    workspace_id=DEMO_WORKSPACE_ID,
    actor="local-demo-reviewer",
) -> dict:
    settings = get_settings()
    storage = settings.storage_dir.resolve()
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    doc_id = uuid4()
    path = storage / f"{doc_id}.pdf"
    digest = hashlib.sha256()
    size = 0
    committing = False
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
            if size == 0 or temporary.read_bytes()[:5] != b"%PDF-":
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
                    if document.sha256 != sha:
                        raise HTTPException(
                            409, "Idempotency key already used for different PDF bytes."
                        )
                    return {
                        "run_id": str(previous.run_id),
                        "document_id": str(document.id),
                        "replayed": True,
                    }
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
            else:
                document = session.get(InvoiceDocument, doc_id)
                persist_document(path, path.name)
                run = ProcessingRun(document_id=doc_id)
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
                )
            )
            audit(
                session,
                workspace_id,
                actor,
                "DOCUMENT_REPLAYED" if replayed else "DOCUMENT_ACCEPTED",
                {"sha256": sha, "filename": Path(filename).name[:255]},
                document.id,
                run.id,
            )
            response = {
                "run_id": str(run.id),
                "document_id": str(document.id),
                "replayed": replayed,
            }
            committing = True
            session.commit()
            return response
        except Exception:
            session.rollback()
            # A failed commit acknowledgement can be ambiguous. Retain the immutable
            # artifact rather than risk deleting a document whose metadata committed.
            if not committing:
                path.unlink(missing_ok=True)
                try:
                    remove_document(path.name)
                except Exception:
                    pass
            raise
        finally:
            temporary.unlink(missing_ok=True)
