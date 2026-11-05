"""Operational views derived only from persisted workspace-scoped records."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import String, func, select
from sqlalchemy.orm import selectinload

from app.auth import User, manual_modes_allowed
from app.config import get_settings
from app.models import (
    AuditEvent,
    BusinessInvoice,
    Decision,
    DocumentSubmission,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
    PurchaseOrder,
    RunEvent,
    Vendor,
    WorkerHeartbeat,
    Workspace,
)
from app.procurement import po_history
from app.workflow_api import DB, run_view
from app.workspace_service import workspace_kind

router = APIRouter(prefix="/api/v1")


@router.get("/me")
def me(session: DB, user: User):
    workspace = session.get(Workspace, user.workspace_id)
    return {
        "subject": user.subject,
        "role": user.role,
        "can_manage_procurement": user.role in ["REVIEWER", "ADMIN"],
        "can_select_extraction_mode": manual_modes_allowed(user),
        "gemini_configured": bool(get_settings().gemini_api_key),
        "supported_currencies": ["USD", "INR", "EUR", "GBP", "JPY", "KWD"],
        "workspace_id": str(user.workspace_id),
        "workspace_kind": workspace_kind(workspace) if workspace else "CUSTOM",
        "vendor_count": session.scalar(
            select(func.count()).select_from(Vendor).where(Vendor.workspace_id == user.workspace_id)
        ),
        "po_count": session.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.workspace_id == user.workspace_id)
        ),
        "workspace_name": workspace.name if workspace else "Unseeded workspace",
    }


@router.get("/dashboard")
def dashboard(
    session: DB,
    user: User,
    outcome: str | None = None,
    vendor: str | None = None,
    search: str | None = None,
):
    documents = session.scalars(
        select(InvoiceDocument).where(InvoiceDocument.workspace_id == user.workspace_id)
    ).all()
    doc_ids = [d.id for d in documents]
    runs = (
        session.scalars(
            select(ProcessingRun)
            .where(ProcessingRun.document_id.in_(doc_ids))
            .order_by(ProcessingRun.created_at.desc())
        ).all()
        if doc_ids
        else []
    )
    decisions = (
        session.scalars(
            select(Decision)
            .join(ProcessingRun)
            .where(ProcessingRun.document_id.in_(doc_ids))
            .order_by(Decision.created_at.desc())
        ).all()
        if doc_ids
        else []
    )
    by_run = {d.run_id: d for d in decisions}
    run_map = {r.id: r for r in runs}
    invoices = session.scalars(
        select(BusinessInvoice).where(BusinessInvoice.workspace_id == user.workspace_id)
    ).all()
    states = []
    canonical_docs = {i.source_document_id for i in invoices}
    for invoice in invoices:
        latest = next(
            (
                d
                for d in decisions
                if d.invoice_id == invoice.id
                and run_map[d.run_id].document_id == invoice.source_document_id
            ),
            None,
        )
        if latest:
            states.append(run_view(session, run_map[latest.run_id], latest))
    for document in documents:
        if document.id in canonical_docs:
            continue
        latest = next((d for d in decisions if run_map[d.run_id].document_id == document.id), None)
        if latest and latest.invoice_id is None:
            states.append(run_view(session, run_map[latest.run_id], latest))

    def matches(item):
        return (
            (not outcome or item["outcome"] == outcome)
            and (not vendor or vendor.casefold() in (item["vendor_name"] or "").casefold())
            and (
                not search
                or search.casefold()
                in ((item["invoice_number"] or "") + " " + (item["vendor_name"] or "")).casefold()
            )
        )

    states = [s for s in states if matches(s)]
    counts = {
        key: sum(s["outcome"] == key for s in states)
        for key in ["VALIDATED", "NEEDS_REVIEW", "BLOCKED"]
    }
    durations = [
        (r.finished_at - r.created_at).total_seconds()
        for r in runs
        if r.finished_at and r.status == "SUCCEEDED"
    ]
    worker = session.scalar(
        select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen.desc()).limit(1)
    )
    duplicates = sum(any(v["rule_id"] == "BUSINESS_DUPLICATE" for v in d.rules) for d in decisions)
    return {
        "total_invoices": len(states),
        "identified_invoices": len(invoices),
        "unidentified_documents": sum(s["invoice_number"] is None for s in states),
        "outcomes": counts,
        "processing_runs": len(runs),
        "failed_runs": sum(r.status == "FAILED" for r in runs),
        "duplicate_assessments": duplicates,
        "submissions": session.scalar(
            select(func.count())
            .select_from(DocumentSubmission)
            .where(DocumentSubmission.workspace_id == user.workspace_id)
        ),
        "average_run_seconds": round(sum(durations) / len(durations), 2) if durations else None,
        "duration_sample_count": len(durations),
        "recent_runs": [
            run_view(session, r, by_run.get(r.id))
            for r in runs
            if matches(run_view(session, r, by_run.get(r.id)))
        ][:20],
        "current_invoices": states,
        "worker": {
            "last_seen": worker.last_seen if worker else None,
            "available": bool(
                worker and worker.last_seen > datetime.now(timezone.utc) - timedelta(minutes=3)
            ),
        },
    }


@router.get("/purchase-orders/{po_id}")
def po_detail(po_id: UUID, session: DB, user: User):
    po = session.scalar(
        select(PurchaseOrder)
        .where(PurchaseOrder.id == po_id, PurchaseOrder.workspace_id == user.workspace_id)
        .options(selectinload(PurchaseOrder.vendor), selectinload(PurchaseOrder.items))
    )
    if not po:
        raise HTTPException(404, "Purchase order not found.")
    commitments = session.scalars(
        select(FinancialCommitment)
        .where(FinancialCommitment.po_id == po.id)
        .order_by(FinancialCommitment.created_at.desc())
    ).all()
    reserved = sum(c.amount for c in commitments if c.status in ["RESERVED", "HELD"])
    settled = sum(c.amount for c in commitments if c.status == "SETTLED")
    return {
        "id": str(po.id),
        "number": po.number,
        "version": po.version,
        "has_history": po_history(session, po),
        "vendor_id": str(po.vendor_id),
        "billing_mode": po.billing_mode,
        "issued_on": po.issued_on,
        "valid_until": po.valid_until,
        "vendor": po.vendor.legal_name,
        "currency": po.currency,
        "status": po.status,
        "authorized": str(po.authorized_gross),
        "reserved": str(reserved),
        "settled": str(settled),
        "available": str(po.authorized_gross - reserved - settled),
        "items": [
            {
                "line_number": i.line_number,
                "sku": i.sku,
                "description": i.description,
                "quantity": str(i.quantity),
                "unit_price": str(i.unit_price),
                "tax_rate": str(i.tax_rate),
            }
            for i in po.items
        ],
        "commitments": [
            {
                "id": str(c.id),
                "invoice_id": str(c.invoice_id),
                "amount": str(c.amount),
                "status": c.status,
                "run_id": str(session.get(Decision, c.decision_id).run_id),
                "created_at": c.created_at,
            }
            for c in commitments
        ],
    }


@router.get("/audit-events")
def audit_history(
    session: DB,
    user: User,
    run_id: UUID | None = None,
    document_id: UUID | None = None,
    view: str = Query("all", pattern="^(all|business)$"),
    search: str = Query("", max_length=160),
    actor: str = Query("", max_length=200),
    stage: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    query = select(AuditEvent).where(AuditEvent.workspace_id == user.workspace_id)
    stage_query = (
        select(RunEvent)
        .join(ProcessingRun)
        .join(InvoiceDocument)
        .where(InvoiceDocument.workspace_id == user.workspace_id)
    )
    if view == "business":
        # Filter persisted records before pagination; never delete the raw audit trail.
        stage_query = stage_query.where(
            ((RunEvent.stage == "decision") & (RunEvent.outcome == "SUCCEEDED"))
            | (RunEvent.outcome == "FAILED")
        )
        query = query.where(AuditEvent.action.not_in(["WORKER_HEARTBEAT"]))
    if actor:
        query = query.where(AuditEvent.actor == actor)
        if actor != "worker":
            stage_query = stage_query.where(False)
    if stage:
        if stage == "REVIEWER_ACTION":
            stage_query = stage_query.where(False)
        else:
            query = query.where(False)
            stage_query = stage_query.where(func.upper(RunEvent.stage) == stage)
    if search:
        term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            AuditEvent.action.ilike(term, escape="\\")
            | AuditEvent.actor.ilike(term, escape="\\")
            | AuditEvent.detail.cast(String).ilike(term, escape="\\")
        )
        stage_query = stage_query.where(
            RunEvent.detail.ilike(term, escape="\\") | RunEvent.stage.ilike(term, escape="\\")
        )
    if run_id:
        query = query.where(AuditEvent.run_id == run_id)
        stage_query = stage_query.where(RunEvent.run_id == run_id)
    if document_id:
        query = query.where(AuditEvent.document_id == document_id)
        stage_query = stage_query.where(ProcessingRun.document_id == document_id)
    audits = session.scalars(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(offset + limit)
    ).all()
    stages = session.scalars(
        stage_query.order_by(RunEvent.created_at.desc(), RunEvent.id.cast(String).desc()).limit(
            offset + limit
        )
    ).all()
    events = [
        {
            "id": str(a.id),
            "action": a.action,
            "actor": a.actor,
            "created_at": a.created_at,
            "run_id": str(a.run_id) if a.run_id else None,
            "document_id": str(a.document_id) if a.document_id else None,
            "detail": a.detail,
        }
        for a in audits
    ]
    events += [
        {
            "id": "stage-" + str(e.id),
            "action": e.stage.upper() + ":" + e.outcome,
            "actor": "worker",
            "created_at": e.created_at,
            "run_id": str(e.run_id),
            "detail": {"attempt": e.attempt, "message": e.detail},
        }
        for e in stages
    ]
    events.sort(key=lambda a: (a["created_at"], a["id"]), reverse=True)
    page = events[offset : offset + limit]
    if view == "business":
        identifiers = {UUID(e["run_id"]) for e in page if e.get("run_id")}
        records = (
            session.execute(
                select(ProcessingRun, Decision)
                .outerjoin(Decision, Decision.run_id == ProcessingRun.id)
                .join(InvoiceDocument)
                .where(
                    InvoiceDocument.workspace_id == user.workspace_id,
                    ProcessingRun.id.in_(identifiers),
                )
            ).all()
            if identifiers
            else []
        )
        entities = {}
        for run, decision in records:
            fields = (run.extraction or {}).get("fields", {})
            summary = decision.summary if decision else {}
            issues = (
                sorted(
                    [r for r in decision.rules if r["outcome"] != "PASS"],
                    key=lambda r: r["outcome"] != "BLOCK",
                )
                if decision
                else []
            )
            entities[str(run.id)] = {
                "invoice_number": fields.get("invoice_number", {}).get("value"),
                "vendor": fields.get("vendor_name", {}).get("value"),
                "amount": summary.get("requested"),
                "currency": summary.get("currency"),
                "outcome": decision.outcome if decision else None,
                "reason": issues[0]["explanation"] if issues else None,
            }
        for item in page:
            item["entity"] = entities.get(item.get("run_id"))
    return {"events": page}
