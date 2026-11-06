from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.audit import audit, financial_lock
from app.auth import Reviewer, User
from app.models import (
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
    ReviewCorrection,
    ReviewTask,
)
from app.review.service import (
    CorrectionInput,
    ReviewActionInput,
    open_review,
    release_held,
    submit_correction,
    task_for_user,
)
from app.workflow_api import DB, run_view, scoped_run

router = APIRouter(prefix="/api/v1")


def task_view(session, task):
    run = session.get(ProcessingRun, task.latest_run_id)
    decision = session.scalar(select(Decision).where(Decision.run_id == run.id))
    return {
        "id": str(task.id),
        "document_id": str(task.document_id),
        "latest_run_id": str(task.latest_run_id),
        "status": task.status,
        "version": task.version,
        "assignee": task.assignee,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "run": run_view(session, run),
        "outcome": decision.outcome if decision else None,
    }


@router.get("/reviews")
def queue(
    session: DB,
    user: User,
    status: str = "OPEN",
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    search: str | None = Query(None, max_length=160),
):
    query = (
        select(ReviewTask)
        .join(InvoiceDocument)
        .where(InvoiceDocument.workspace_id == user.workspace_id)
    )
    if search:
        term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.join(ProcessingRun, ProcessingRun.id == ReviewTask.latest_run_id).where(
            or_(
                *(
                    ProcessingRun.extraction["fields"][field]["value"].astext.ilike(
                        term, escape="\\"
                    )
                    for field in ["invoice_number", "vendor_name", "po_number"]
                )
            )
        )
    if status != "ALL":
        query = query.where(
            ReviewTask.status.in_(["OPEN", "REVALIDATING"])
            if status == "OPEN"
            else ReviewTask.status == status
        )
    tasks = session.scalars(
        query.order_by(ReviewTask.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return {"tasks": [task_view(session, t) for t in tasks]}


@router.get("/reviews/{task_id}")
def review_detail(task_id: UUID, session: DB, user: User):
    task = task_for_user(session, task_id, user)
    run = session.get(ProcessingRun, task.latest_run_id)
    corrections = session.scalars(
        select(ReviewCorrection)
        .where(ReviewCorrection.task_id == task.id)
        .order_by(ReviewCorrection.created_at)
    ).all()
    decisions = session.scalars(
        select(Decision)
        .join(ProcessingRun)
        .where(ProcessingRun.document_id == task.document_id)
        .order_by(Decision.created_at)
    ).all()
    commitments = (
        session.scalars(
            select(FinancialCommitment).where(FinancialCommitment.invoice_id == task.invoice_id)
        ).all()
        if task.invoice_id
        else []
    )
    return {
        **task_view(session, task),
        "extraction": run.extraction,
        "corrections": [
            {
                "id": str(c.id),
                "run_id": str(c.run_id),
                "actor": c.actor,
                "comment": c.comment,
                "created_at": c.created_at,
                "extraction": c.extraction,
            }
            for c in corrections
        ],
        "decisions": [
            {
                "run_id": str(d.run_id),
                "outcome": d.outcome,
                "rules": d.rules,
                "created_at": d.created_at,
            }
            for d in decisions
        ],
        "commitments": [
            {"id": str(c.id), "amount": str(c.amount), "currency": c.currency, "status": c.status}
            for c in commitments
        ],
    }


@router.post("/runs/{run_id}/review")
def request_review(run_id: UUID, session: DB, user: Reviewer):
    run = scoped_run(session, run_id, user.workspace_id)
    task = open_review(
        session, run, user, "Reviewer requested a source correction or reassessment."
    )
    session.commit()
    return task_view(session, task)


@router.post("/reviews/{task_id}/corrections", status_code=202)
def correct(task_id: UUID, payload: CorrectionInput, session: DB, user: Reviewer):
    run, task = submit_correction(session, task_id, user, payload)
    response = {"run_id": str(run.id), "task_id": str(task.id), "version": task.version}
    session.commit()
    return response


@router.post("/reviews/{task_id}/claim")
def claim_review(task_id: UUID, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    task = task_for_user(session, task_id, user, True)
    if task.status != "OPEN":
        raise HTTPException(409, "Review is not open.")
    if task.assignee and task.assignee != user.subject:
        raise HTTPException(409, "This review is assigned to another reviewer.")
    task.assignee = user.subject
    task.version += 1
    audit(
        session,
        user.workspace_id,
        user.subject,
        "REVIEW_CLAIMED",
        {"task_id": str(task.id)},
        task.document_id,
        task.latest_run_id,
    )
    session.commit()
    return task_view(session, task)


@router.post("/reviews/{task_id}/release")
def release(task_id: UUID, payload: ReviewActionInput, session: DB, user: Reviewer):
    task = release_held(session, task_id, user, payload)
    session.commit()
    return task_view(session, task)
