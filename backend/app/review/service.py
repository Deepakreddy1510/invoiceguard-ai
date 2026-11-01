from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.audit import audit, financial_lock
from app.extraction.schema import FIELDS, InvoiceExtraction
from app.models import (
    BusinessInvoice,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    InvoiceRevision,
    ProcessingRun,
    ReviewCorrection,
    ReviewTask,
    RunEvent,
)


class CorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    comment: str = Field(min_length=10, max_length=2000)
    values: dict[str, str | None] = Field(default_factory=dict)
    items: list[dict[str, str | None]] | None = None


class ReviewActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    comment: str = Field(min_length=10, max_length=2000)


def ensure_task(session, run, invoice_id=None):
    task = session.scalar(
        select(ReviewTask)
        .where(
            ReviewTask.document_id == run.document_id,
            ReviewTask.status.in_(["OPEN", "REVALIDATING"]),
        )
        .with_for_update()
    )
    if not task:
        task = ReviewTask(document_id=run.document_id, latest_run_id=run.id, invoice_id=invoice_id)
        session.add(task)
        session.flush()
    else:
        task.latest_run_id = run.id
        task.invoice_id = invoice_id or task.invoice_id
        task.status = "OPEN"
        task.version += 1
        task.updated_at = datetime.now(timezone.utc)
    return task


def task_for_user(session, task_id, user, lock=False):
    query = (
        select(ReviewTask)
        .join(InvoiceDocument)
        .where(ReviewTask.id == task_id, InvoiceDocument.workspace_id == user.workspace_id)
    )
    if lock:
        query = query.with_for_update(of=ReviewTask)
    task = session.scalar(query)
    if not task:
        raise HTTPException(404, "Review task not found.")
    return task


def hold(session, invoice_id, workspace, actor, document_id, run_id):
    if not invoice_id:
        return
    for commitment in session.scalars(
        select(FinancialCommitment)
        .where(
            FinancialCommitment.invoice_id == invoice_id, FinancialCommitment.status == "RESERVED"
        )
        .with_for_update()
    ).all():
        commitment.status = "HELD"
        audit(
            session,
            workspace,
            actor,
            "RESERVATION_HELD",
            {"commitment_id": str(commitment.id), "amount": str(commitment.amount)},
            document_id,
            run_id,
        )


def open_review(session, run, user, comment):
    financial_lock(session, user.workspace_id)
    decision = session.scalar(select(Decision).where(Decision.run_id == run.id))
    if not decision:
        raise HTTPException(409, "Wait for a completed business decision before requesting review.")
    invoice = session.get(BusinessInvoice, decision.invoice_id) if decision.invoice_id else None
    if invoice and invoice.source_document_id != run.document_id:
        raise HTTPException(
            409,
            "Review the original invoice; a duplicate submission cannot change its financial reservation.",
        )
    current = session.scalar(
        select(ReviewTask).where(
            ReviewTask.document_id == run.document_id,
            ReviewTask.status.in_(["OPEN", "REVALIDATING"]),
        )
    )
    if current:
        return current
    task = ensure_task(session, run, decision.invoice_id)
    hold(session, decision.invoice_id, user.workspace_id, user.subject, run.document_id, run.id)
    audit(
        session,
        user.workspace_id,
        user.subject,
        "REVIEW_OPENED",
        {"task_id": str(task.id), "comment": comment},
        run.document_id,
        run.id,
    )
    return task


def submit_correction(session, task_id, user, payload: CorrectionInput):
    financial_lock(session, user.workspace_id)
    task = task_for_user(session, task_id, user, True)
    if task.version != payload.version:
        raise HTTPException(409, "This review changed. Reload before saving your correction.")
    if task.status != "OPEN":
        raise HTTPException(409, "Review is not open for correction.")
    if not payload.values and payload.items is None:
        raise HTTPException(
            422, "Correct or explicitly confirm at least one source field before revalidation."
        )
    if task.assignee and task.assignee != user.subject and user.role != "ADMIN":
        raise HTTPException(409, "This task is assigned to another reviewer.")
    unknown = set(payload.values) - set(FIELDS)
    if unknown:
        raise HTTPException(422, "Unknown correction fields: " + ", ".join(sorted(unknown)))
    parent = session.get(ProcessingRun, task.latest_run_id)
    if not parent.extraction:
        raise HTTPException(409, "No extracted data available; retry document processing first.")
    extraction = deepcopy(parent.extraction)
    fields = extraction["fields"]

    def human(value):
        return {"value": value, "page": None, "quote": None}

    for field, value in payload.values.items():
        fields[field] = human(value)
    if payload.items is not None:
        if len(payload.items) > 200:
            raise HTTPException(422, "At most 200 line items are supported.")
        required = {"sku", "quantity", "unit_price", "net", "tax_rate", "tax", "gross"}
        if any(set(item) != required for item in payload.items):
            raise HTTPException(
                422,
                "Each item must contain SKU, quantity, unit_price, net, tax_rate, tax and gross.",
            )
        fields["items"] = [{k: human(v) for k, v in item.items()} for item in payload.items]
    # Validate schema, strip all client-controlled verification attributes.
    raw = {k: v for k, v in fields.items() if k not in ["items", "issues"]}
    for k, v in list(raw.items()):
        if isinstance(v, dict):
            raw[k] = {n: v.get(n) for n in ["value", "page", "quote"]}
    raw["items"] = [
        {k: {n: v.get(n) for n in ["value", "page", "quote"]} for k, v in item.items()}
        for item in fields.get("items", [])
    ]
    raw["issues"] = []
    try:
        InvoiceExtraction.model_validate(raw)
    except ValueError as exc:
        raise HTTPException(422, "Correction does not match the invoice field schema.") from exc
    # Retain original evidence on unchanged values. Corrections have explicit human provenance.
    for field in payload.values:
        fields[field].update(
            verified=fields[field]["value"] is not None,
            method="HUMAN",
            document_id=str(task.document_id),
            reviewer=user.subject,
        )
    if payload.items is not None:
        for item in fields["items"]:
            for value in item.values():
                value.update(
                    verified=value["value"] is not None,
                    method="HUMAN",
                    document_id=str(task.document_id),
                    reviewer=user.subject,
                )
    # Source ambiguities can be resolved only by a reviewer attesting the complete revision.
    # Unchanged unsupported fields keep verified=False and cannot pass required checks.
    fields["issues"] = []
    extraction.update(
        provider="HUMAN_REVIEW", reviewer=user.subject, review_comment=payload.comment
    )
    run = ProcessingRun(
        document_id=task.document_id,
        parent_run_id=parent.id,
        status="QUEUED",
        pages=parent.pages,
        extraction=extraction,
    )
    session.add(run)
    session.flush()
    session.add(
        ReviewCorrection(
            task_id=task.id,
            run_id=run.id,
            base_run_id=parent.id,
            actor=user.subject,
            comment=payload.comment,
            extraction=extraction,
        )
    )
    session.add(
        RunEvent(
            run_id=run.id,
            attempt=0,
            stage="review",
            outcome="QUEUED",
            detail="Attributed correction saved; full financial revalidation queued.",
        )
    )
    task.status = "REVALIDATING"
    task.latest_run_id = run.id
    task.version += 1
    task.assignee = user.subject
    task.updated_at = datetime.now(timezone.utc)
    hold(session, task.invoice_id, user.workspace_id, user.subject, task.document_id, run.id)
    audit(
        session,
        user.workspace_id,
        user.subject,
        "CORRECTION_SAVED",
        {
            "task_id": str(task.id),
            "comment": payload.comment,
            "changed_fields": list(payload.values),
            "items_replaced": payload.items is not None,
            "base_run_id": str(parent.id),
            "extraction": extraction,
        },
        task.document_id,
        run.id,
    )
    return run, task


def release_held(session, task_id, user, payload: ReviewActionInput):
    financial_lock(session, user.workspace_id)
    task = task_for_user(session, task_id, user, True)
    if task.status == "RESOLVED":
        return task
    if task.version != payload.version:
        raise HTTPException(409, "This review changed. Reload before releasing.")
    if task.status == "REVALIDATING":
        raise HTTPException(409, "Cannot release while financial revalidation is running.")
    if task.invoice_id:
        invoice = session.get(BusinessInvoice, task.invoice_id)
        if not invoice or invoice.source_document_id != task.document_id:
            raise HTTPException(
                409, "Duplicate reviews cannot release the original invoice's reservation."
            )
    commitments = (
        session.scalars(
            select(FinancialCommitment)
            .where(
                FinancialCommitment.invoice_id == task.invoice_id,
                FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"]),
            )
            .with_for_update()
        ).all()
        if task.invoice_id
        else []
    )
    if any(c.status == "SETTLED" for c in commitments):
        raise HTTPException(409, "Settled commitments cannot be released by invoice review.")
    for c in commitments:
        c.status = "RELEASED"
        audit(
            session,
            user.workspace_id,
            user.subject,
            "RESERVATION_RELEASED",
            {"commitment_id": str(c.id), "amount": str(c.amount), "comment": payload.comment},
            task.document_id,
            task.latest_run_id,
        )
    parent = session.get(ProcessingRun, task.latest_run_id)
    previous = session.scalar(
        select(Decision)
        .join(ProcessingRun)
        .where(ProcessingRun.document_id == task.document_id)
        .order_by(Decision.created_at.desc())
        .limit(1)
    )
    rejected = ProcessingRun(
        document_id=task.document_id,
        parent_run_id=parent.id,
        status="SUCCEEDED",
        attempt=0,
        pages=parent.pages,
        extraction=parent.extraction,
        finished_at=datetime.now(timezone.utc),
    )
    session.add(rejected)
    session.flush()
    revision = InvoiceRevision(
        invoice_id=task.invoice_id, run_id=rejected.id, extraction=parent.extraction or {}
    )
    session.add(revision)
    session.flush()
    decision = Decision(
        run_id=rejected.id,
        revision_id=revision.id,
        invoice_id=task.invoice_id,
        po_id=previous.po_id if previous else None,
        outcome="BLOCKED",
        rules=[
            {
                "rule_id": "REVIEW_REJECTED",
                "outcome": "BLOCK",
                "explanation": "Reviewer rejected this invoice: " + payload.comment,
                "actual": None,
                "expected": None,
            }
        ],
        summary={
            "manual_rejection": True,
            "payment_executed": False,
            "released_commitment_ids": [str(c.id) for c in commitments],
        },
    )
    session.add(decision)
    session.add(
        RunEvent(
            run_id=rejected.id,
            attempt=0,
            stage="review_disposition",
            outcome="SUCCEEDED",
            detail="Reviewer rejected the case and released any unsettled hold. No extraction or automated validation was executed in this disposition run.",
        )
    )
    task.latest_run_id = rejected.id
    task.status = "RESOLVED"
    task.version += 1
    task.updated_at = datetime.now(timezone.utc)
    audit(
        session,
        user.workspace_id,
        user.subject,
        "REVIEW_CLOSED",
        {"task_id": str(task.id), "comment": payload.comment},
        task.document_id,
        task.latest_run_id,
    )
    return task
