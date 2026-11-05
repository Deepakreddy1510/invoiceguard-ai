"""Durable database-backed worker. Run with python -m app.worker.main."""

import argparse
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import or_, select

from app.audit import audit, financial_lock
from app.config import get_settings
from app.db import SessionLocal
from app.extraction.pdf import pdf_process
from app.extraction.pipeline import ExtractionModeFailure, structure
from app.models import (
    BusinessInvoice,
    CommitmentAllocation,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    InvoiceRevision,
    ProcessingRun,
    ReviewCorrection,
    ReviewTask,
    RunEvent,
    WorkerHeartbeat,
    Workspace,
)
from app.review.service import ensure_task, hold
from app.validation.engine import evaluate

logger = logging.getLogger(__name__)


class LostLease(RuntimeError):
    pass


def owned(session, run_id, token):
    run = session.scalar(select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update())
    if not run or run.status != "RUNNING" or run.lease_token != token:
        raise LostLease("Run ownership changed; stale worker cannot write.")
    return run


def event(session, run, stage, outcome, detail):
    session.add(
        RunEvent(
            run_id=run.id,
            attempt=run.attempt,
            stage=stage,
            outcome=outcome,
            detail=detail[:500],
            created_at=datetime.now(timezone.utc),
        )
    )


def claim(factory=SessionLocal, run_id=None):
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        # Lock the workspace before the queue row so archive and claim cannot race.
        candidate = session.scalar(
            select(Workspace)
            .join(InvoiceDocument, InvoiceDocument.workspace_id == Workspace.id)
            .join(ProcessingRun, ProcessingRun.document_id == InvoiceDocument.id)
            .where(
                Workspace.archived_at.is_(None),
                ProcessingRun.id == run_id if run_id else True,
                or_(
                    ProcessingRun.status.in_(["QUEUED", "RETRY_WAIT"]),
                    (ProcessingRun.status == "RUNNING") & (ProcessingRun.lease_until < now),
                ),
            )
            .order_by(ProcessingRun.created_at)
            .limit(1)
        )
        if candidate is None:
            return None
        workspace = session.scalar(
            select(Workspace)
            .where(Workspace.id == candidate.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if workspace.archived_at:
            return None
        run = session.scalar(
            select(ProcessingRun)
            .join(InvoiceDocument)
            .where(InvoiceDocument.workspace_id == workspace.id)
            .where(ProcessingRun.id == run_id if run_id else True)
            .where(
                or_(
                    ProcessingRun.status.in_(["QUEUED", "RETRY_WAIT"]),
                    (ProcessingRun.status == "RUNNING") & (ProcessingRun.lease_until < now),
                )
            )
            .order_by(ProcessingRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if run is None:
            return None
        if run.attempt >= 3:
            run.status = "FAILED"
            run.error = "Worker interrupted repeatedly; explicit retry required."
            run.finished_at = now
            event(session, run, "worker", "FAILED", run.error)
            task = session.scalar(
                select(ReviewTask).where(
                    ReviewTask.latest_run_id == run.id, ReviewTask.status == "REVALIDATING"
                )
            )
            if task:
                task.status = "OPEN"
                task.version += 1
                task.updated_at = now
            return None
        if run.status == "RUNNING":
            event(
                session,
                run,
                "worker",
                "RETRY_WAIT",
                "Expired worker lease reclaimed; unfinished stages will execute again.",
            )
        run.status = "RUNNING"
        run.attempt += 1
        run.lease_token = uuid4()
        run.lease_until = now + timedelta(seconds=180)
        event(session, run, "worker", "RUNNING", "Worker claimed durable run.")
        document = session.get(InvoiceDocument, run.document_id)
        return run.id, run.lease_token, document.storage_key, str(document.id)


def save_stage(factory, run_id, token, stage, outcome, detail, **changes):
    with factory.begin() as session:
        run = owned(session, run_id, token)
        for name, value in changes.items():
            setattr(run, name, value)
        event(session, run, stage, outcome, detail)
        if changes.get("status") == "FAILED":
            correction = session.scalar(
                select(ReviewCorrection).where(ReviewCorrection.run_id == run_id)
            )
            task = (
                session.get(ReviewTask, correction.task_id)
                if correction
                else session.scalar(
                    select(ReviewTask).where(
                        ReviewTask.latest_run_id == run_id, ReviewTask.status == "REVALIDATING"
                    )
                )
            )
            if task:
                task.status = "OPEN"
                task.version += 1
                task.updated_at = datetime.now(timezone.utc)


def finalize(session, run_id, token):
    run = session.get(ProcessingRun, run_id)
    if run is None:
        raise LostLease("Run disappeared.")
    document = session.get(InvoiceDocument, run.document_id)
    financial_lock(session, document.workspace_id)
    run = owned(session, run_id, token) if run.status != "SUCCEEDED" else run
    existing = session.scalar(select(Decision).where(Decision.run_id == run_id))
    if existing:
        return existing
    correction = session.scalar(select(ReviewCorrection).where(ReviewCorrection.run_id == run_id))
    task = (
        session.get(ReviewTask, correction.task_id)
        if correction
        else session.scalar(
            select(ReviewTask).where(
                ReviewTask.latest_run_id == run_id, ReviewTask.status == "REVALIDATING"
            )
        )
    )
    original = (
        session.get(BusinessInvoice, task.invoice_id)
        if task and task.invoice_id
        else session.scalar(
            select(BusinessInvoice).where(
                BusinessInvoice.workspace_id == document.workspace_id,
                BusinessInvoice.source_document_id == run.document_id,
            )
        )
    )
    if original and original.source_document_id != run.document_id:
        original = None
    replacing = original.id if original else None
    event(
        session,
        run,
        "validation",
        "RUNNING",
        "Evaluating every financial control against current locked PO capacity.",
    )
    outcome, rules, summary, invoice, po, allocations = evaluate(
        session, run, run.extraction, replacing
    )
    if run.intake_context:
        from app.email_intake.policy import POLICY_VERSION, assess

        email_rules = assess(run.intake_context, run.extraction)
        rules.extend(email_rules)
        summary["email_context"] = run.intake_context
        if outcome == "VALIDATED" and any(r["outcome"] == "REVIEW" for r in email_rules):
            outcome = "NEEDS_REVIEW"
        event(
            session,
            run,
            "email_matching",
            "SUCCEEDED",
            POLICY_VERSION + ": email evidence assessed separately from PDF evidence.",
        )
    invoice = invoice or original
    revision = InvoiceRevision(
        invoice_id=invoice.id if invoice else None, run_id=run.id, extraction=run.extraction
    )
    session.add(revision)
    session.flush()
    decision = Decision(
        run_id=run.id,
        revision_id=revision.id,
        invoice_id=invoice.id if invoice else None,
        po_id=po.id if po else None,
        outcome=outcome,
        rules=rules,
        summary=summary,
        **(
            {"policy_version": "gross-zero-overrun-v1+email-po-review-v1"}
            if run.intake_context
            else {}
        ),
    )
    decision.id = uuid4()
    if outcome == "VALIDATED":
        previous = session.scalars(
            select(FinancialCommitment)
            .where(
                FinancialCommitment.invoice_id == invoice.id,
                FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"]),
            )
            .with_for_update()
        ).all()
        if any(c.status == "SETTLED" for c in previous):
            raise RuntimeError("Settled invoices require external AP reconciliation.")
        for c in previous:
            c.status = "RELEASED"
            audit(
                session,
                document.workspace_id,
                "worker",
                "RESERVATION_REPLACED",
                {"commitment_id": str(c.id), "amount": str(c.amount)},
                document.id,
                run.id,
            )
        session.flush()  # Release old partial-unique-index entry before insertion.
        commitment = FinancialCommitment(
            id=uuid4(),
            invoice_id=invoice.id,
            decision_id=decision.id,
            po_id=po.id,
            amount=Decimal(summary["requested"]),
            currency=po.currency,
        )
        summary = {
            **summary,
            "commitment_id": str(commitment.id),
            "available_after": str(Decimal(summary["available_before"]) - commitment.amount),
        }
        decision.summary = summary
        session.add(decision)
        session.flush()
        session.add(commitment)
        session.flush()
        for item_id, quantity in allocations.items():
            session.add(
                CommitmentAllocation(
                    commitment_id=commitment.id, po_item_id=item_id, quantity=quantity
                )
            )
        audit(
            session,
            document.workspace_id,
            "worker",
            "RESERVATION_CREATED",
            {
                "commitment_id": str(commitment.id),
                "amount": str(commitment.amount),
                "currency": po.currency,
            },
            document.id,
            run.id,
        )
        if task:
            task.status = "RESOLVED"
            task.version += 1
            task.latest_run_id = run.id
            task.invoice_id = invoice.id
    elif outcome == "NEEDS_REVIEW" or task:
        hold(session, replacing, document.workspace_id, "worker", document.id, run.id)
        task = ensure_task(
            session,
            run,
            invoice.id if invoice and invoice.source_document_id == document.id else None,
        )
    session.add(decision)
    if task:
        task.updated_at = datetime.now(timezone.utc)
    event(session, run, "validation", "SUCCEEDED", f"Deterministic evaluation complete: {outcome}.")
    event(session, run, "decision", "SUCCEEDED", f"{outcome}. Validation never executes payment.")
    audit(
        session,
        document.workspace_id,
        "worker",
        "DECISION_RECORDED",
        {
            "decision_id": str(decision.id),
            "outcome": outcome,
            "policy_version": decision.policy_version or "gross-zero-overrun-v1",
            "review_task_id": str(task.id) if task else None,
        },
        document.id,
        run.id,
    )
    run.status = "SUCCEEDED"
    run.finished_at = datetime.now(timezone.utc)
    run.lease_until = None
    run.error = None
    return decision


def process(job, factory=SessionLocal):
    run_id, token, storage_key, document_id = job
    stage = "text_extraction"
    try:
        save_stage(
            factory,
            run_id,
            token,
            stage,
            "RUNNING",
            "Reading actual PDF pages; image pages use Tesseract.",
        )
        with factory() as session:
            correction = session.scalar(
                select(ReviewCorrection).where(ReviewCorrection.run_id == run_id)
            )
            revised = correction.extraction if correction else None
            mode = session.get(ProcessingRun, run_id).extraction_mode
        if revised:
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "SKIPPED",
                "Reusing the original document evidence; this run applies an audited human correction.",
            )
            save_stage(
                factory,
                run_id,
                token,
                "ocr",
                "SKIPPED",
                "Original OCR evidence retained; no OCR executed again.",
            )
            stage = "field_extraction"
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "RUNNING",
                "Loading the attributed reviewer revision.",
            )
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "SUCCEEDED",
                "Human correction loaded; all deterministic financial rules will run.",
                extraction=revised,
            )
        else:
            from app.storage import open_document

            with open_document(storage_key) as path:
                with factory() as session:
                    document = session.get(InvoiceDocument, UUID(document_id))
                    expected_hash = document.sha256
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError("Stored document integrity check failed.")
                payload = pdf_process(path, True)
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "SUCCEEDED",
                f"Read {len(payload['pages'])} page(s).",
                pages=payload["pages"],
            )
            ocr_pages = [str(p["page"]) for p in payload["pages"] if p["method"] == "OCR"]
            save_stage(
                factory,
                run_id,
                token,
                "ocr",
                "SUCCEEDED" if ocr_pages else "SKIPPED",
                "OCR executed on pages " + ", ".join(ocr_pages)
                if ocr_pages
                else "No scanned pages required OCR.",
            )
            stage = "field_extraction"
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "RUNNING",
                "Structuring invoice facts and checking source evidence.",
            )
            extraction = (
                structure(payload["pages"], document_id)
                if mode == "AUTO"
                else structure(payload["pages"], document_id, mode)
            )
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "SUCCEEDED",
                extraction["provider"]
                + ": "
                + (extraction["fallback_reason"] or "Structured response evidence checked."),
                extraction=extraction,
            )
        stage = "validation"
        with factory.begin() as session:
            finalize(session, run_id, token)
    except ExtractionModeFailure as exc:
        save_stage(
            factory,
            run_id,
            token,
            stage,
            "FAILED",
            str(exc),
            status="FAILED",
            extraction=exc.metadata,
            error=str(exc),
            finished_at=datetime.now(timezone.utc),
            lease_until=None,
        )
    except LostLease:
        logger.warning("Run %s lost ownership; no stale writes allowed.", run_id)
    except Exception:
        # Avoid raw exception bodies: provider/document data and credentials must not enter logs.
        logger.error("Run %s failed at %s; see persisted safe error.", run_id, stage)
        try:
            save_stage(
                factory,
                run_id,
                token,
                stage,
                "FAILED",
                "Technical failure; no business decision was generated.",
                status="FAILED",
                error=f"{stage} failed. Check document readability, OCR installation, storage and database; retry after correction.",
                finished_at=datetime.now(timezone.utc),
                lease_until=None,
            )
        except LostLease:
            pass


def run_once(factory=SessionLocal, run_id=None):
    job = claim(factory, run_id)
    if job:
        process(job, factory)
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    get_settings().validate_runtime()
    worker_id = uuid4()

    def heartbeat(status):
        with SessionLocal.begin() as session:
            record = session.get(WorkerHeartbeat, worker_id)
            if not record:
                record = WorkerHeartbeat(
                    id=worker_id, last_seen=datetime.now(timezone.utc), status=status
                )
                session.add(record)
            else:
                record.last_seen = datetime.now(timezone.utc)
                record.status = status

    while True:
        try:
            heartbeat("AVAILABLE")
            worked = run_once()
            from app.email_intake.service import mail_once

            mail_worked = mail_once()
            worked = worked or mail_worked
            heartbeat("AVAILABLE")
        except Exception:
            logger.error(
                "Worker dependency failure; retrying shortly without discarding queued work."
            )
            time.sleep(5)
            continue
        if args.once:
            break
        if not worked:
            time.sleep(1)
