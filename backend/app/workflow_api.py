from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit, financial_lock
from app.auth import Reviewer, User
from app.config import DEMO_WORKSPACE_ID, get_settings
from app.db import get_session
from app.ingestion import ingest
from app.models import (
    BusinessInvoice,
    Decision,
    InvoiceDocument,
    ProcessingRun,
    ReviewCorrection,
    ReviewTask,
    RunEvent,
)

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_session)]


def scoped_run(session, run_id, workspace_id=DEMO_WORKSPACE_ID):
    run = session.scalar(
        select(ProcessingRun)
        .join(InvoiceDocument)
        .where(ProcessingRun.id == run_id, InvoiceDocument.workspace_id == workspace_id)
    )
    if not run:
        raise HTTPException(404, "Run not found.")
    return run


_UNSET = object()


def run_view(session, run, decision=_UNSET):
    if decision is _UNSET:
        decision = session.scalar(select(Decision).where(Decision.run_id == run.id))
    return {
        "id": str(run.id),
        "document_id": str(run.document_id),
        "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
        "status": run.status,
        "attempt": run.attempt,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "outcome": decision.outcome if decision else None,
        "invoice_number": (run.extraction or {})
        .get("fields", {})
        .get("invoice_number", {})
        .get("value"),
        "vendor_name": (run.extraction or {}).get("fields", {}).get("vendor_name", {}).get("value"),
    }


@router.post("/documents", status_code=202)
def upload(
    session: DB,
    user: Reviewer,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str | None, Header(max_length=100)] = None,
):
    return ingest(
        file.file,
        file.filename or "invoice.pdf",
        idempotency_key,
        session,
        user.workspace_id,
        user.subject,
    )


@router.get("/documents/{document_id}/content")
def content(document_id: UUID, session: DB, user: User):
    workspace_id = user.workspace_id
    document = session.scalar(
        select(InvoiceDocument).where(
            InvoiceDocument.id == document_id, InvoiceDocument.workspace_id == workspace_id
        )
    )
    if not document:
        raise HTTPException(404, "Document not found.")
    if get_settings().storage_backend == "s3":
        from app.storage import client, key

        body = client().get_object(Bucket=get_settings().s3_bucket, Key=key(document.storage_key))[
            "Body"
        ]

        def stream():
            try:
                yield from body.iter_chunks(65536)
            finally:
                body.close()

        return StreamingResponse(
            stream(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="invoice.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    path = get_settings().storage_dir.resolve() / Path(document.storage_key).name
    if not path.is_file():
        raise HTTPException(404, "Document storage artifact unavailable.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="invoice.pdf",
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "no-store",
        },
    )


@router.get("/runs")
def history(
    session: DB,
    user: User,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    workspace_id = user.workspace_id
    runs = session.scalars(
        select(ProcessingRun)
        .join(InvoiceDocument)
        .where(InvoiceDocument.workspace_id == workspace_id)
        .order_by(ProcessingRun.created_at.desc(), ProcessingRun.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "runs": [run_view(session, r) for r in runs],
        "offset": offset,
        "limit": limit,
        "unique_business_invoices": session.scalar(
            select(func.count())
            .select_from(BusinessInvoice)
            .where(BusinessInvoice.workspace_id == workspace_id)
        ),
    }


@router.get("/runs/{run_id}")
def detail(run_id: UUID, session: DB, user: User):
    run = scoped_run(session, run_id, user.workspace_id)
    decision = session.scalar(select(Decision).where(Decision.run_id == run_id))
    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id)
    ).all()
    return {
        **run_view(session, run),
        "review_task_id": str(task.id)
        if (
            task := session.scalar(
                select(ReviewTask)
                .where(ReviewTask.document_id == run.document_id)
                .order_by(ReviewTask.created_at.desc())
                .limit(1)
            )
        )
        else None,
        "extraction": run.extraction,
        "pages": run.pages,
        "events": [
            {
                "id": e.id,
                "stage": e.stage,
                "outcome": e.outcome,
                "attempt": e.attempt,
                "detail": e.detail,
                "created_at": e.created_at,
            }
            for e in events
        ],
        "decision": {
            "id": str(decision.id),
            "outcome": decision.outcome,
            "rules": decision.rules,
            "summary": decision.summary,
            "policy_version": decision.policy_version,
            "created_at": decision.created_at,
        }
        if decision
        else None,
    }


@router.post("/runs/{run_id}/retry", status_code=202)
def retry(run_id: UUID, session: DB, user: Reviewer):
    scoped_run(session, run_id, user.workspace_id)
    financial_lock(session, user.workspace_id)
    parent = session.scalar(
        select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update()
    )
    if parent.status == "SUCCEEDED":
        return {"run_id": str(parent.id), "replayed": True}
    if parent.status != "FAILED":
        raise HTTPException(409, "Only failed runs can be retried.")
    child = session.scalar(
        select(ProcessingRun)
        .where(ProcessingRun.parent_run_id == parent.id)
        .order_by(ProcessingRun.created_at.desc())
        .limit(1)
    )
    if child:
        return {"run_id": str(child.id), "replayed": True}
    run = ProcessingRun(document_id=parent.document_id, parent_run_id=parent.id, status="QUEUED")
    session.add(run)
    session.flush()
    session.add(
        RunEvent(
            run_id=run.id,
            attempt=0,
            stage="retry",
            outcome="QUEUED",
            detail=f"Explicit retry requested for {parent.id}; previous failure remains in history.",
        )
    )
    correction = session.scalar(
        select(ReviewCorrection).where(ReviewCorrection.run_id == parent.id)
    )
    if correction:
        task = session.get(ReviewTask, correction.task_id)
        if task.status != "OPEN":
            raise HTTPException(409, "Review is already being revalidated.")
        session.add(
            ReviewCorrection(
                task_id=task.id,
                run_id=run.id,
                base_run_id=correction.base_run_id,
                actor=correction.actor,
                comment=correction.comment,
                extraction=correction.extraction,
            )
        )
        run.pages = parent.pages
        run.extraction = correction.extraction
        task.latest_run_id = run.id
        task.status = "REVALIDATING"
        task.version += 1
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PROCESSING_RETRY_REQUESTED",
        {"parent_run_id": str(parent.id)},
        run.document_id,
        run.id,
    )
    session.commit()
    return {"run_id": str(run.id), "replayed": False}
