"""Ordered, resumable sample ingestion; decisions always come from the normal worker."""

from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.audit import audit, financial_lock
from app.ingestion import ingest
from app.models import (
    AuditEvent,
    Decision,
    FinancialCommitment,
    GmailConnection,
    GmailOAuthAttempt,
    InvoiceDocument,
    Membership,
    ProcessingRun,
    PurchaseOrder,
    PurchaseOrderItem,
    RunEvent,
    SampleInstallation,
    Vendor,
    Workspace,
)
from scripts.install_asterfield_demo import ROOT, VERSION, cases, catalogue


def sample_id(subject):
    return uuid5(NAMESPACE_URL, "invoiceguard:sample:" + subject)


def is_owned_sample(session, workspace, subject):
    return bool(
        workspace
        and workspace.owner_subject == subject
        and workspace.kind == "DEMO"
        and (
            workspace.id == sample_id(subject)
            or session.scalar(
                select(AuditEvent.id)
                .where(
                    AuditEvent.workspace_id == workspace.id,
                    AuditEvent.actor == subject,
                    AuditEvent.action == "SAMPLE_COMPANY_CREATED",
                )
                .limit(1)
            )
        )
    )


def start(session, workspace, user):
    # A membership or a similar workspace name is not sufficient to install sample data.
    if not is_owned_sample(session, workspace, user.subject):
        raise HTTPException(403, "Only your isolated Asterfield sample may be initialized.")
    if (
        session.scalar(
            select(Membership.role).where(
                Membership.workspace_id == workspace.id, Membership.subject == user.subject
            )
        )
        != "ADMIN"
    ):
        raise HTTPException(403, "Workspace administrator access is required.")
    financial_lock(session, workspace.id)
    existing = session.get(SampleInstallation, workspace.id)
    if existing:
        return existing
    # Explicit safe backfill: never add scenarios to a workspace with any invoice history.
    if session.scalar(
        select(InvoiceDocument.id).where(InvoiceDocument.workspace_id == workspace.id).limit(1)
    ) or session.scalar(
        select(FinancialCommitment.id)
        .join(PurchaseOrder)
        .where(PurchaseOrder.workspace_id == workspace.id)
        .limit(1)
    ):
        raise HTTPException(
            409,
            "This sample already has invoice history. Existing records will not be reprocessed.",
        )
    if session.scalar(
        select(GmailConnection.id).where(GmailConnection.workspace_id == workspace.id).limit(1)
    ):
        raise HTTPException(
            409, "This sample has a Gmail connection. Existing mailbox data will not be changed."
        )
    if session.scalar(
        select(GmailOAuthAttempt.id).where(GmailOAuthAttempt.workspace_id == workspace.id).limit(1)
    ):
        raise HTTPException(
            409,
            "This sample has Gmail authorization history. Existing mailbox setup will not be changed.",
        )
    catalog = catalogue()
    vendors = session.scalars(select(Vendor).where(Vendor.workspace_id == workspace.id)).all()
    pos = session.scalars(
        select(PurchaseOrder).where(PurchaseOrder.workspace_id == workspace.id)
    ).all()
    if len(vendors) != 18 or len(pos) != 36:
        raise HTTPException(
            409, "Sample procurement was changed. Existing records will not be overwritten."
        )
    for source in catalog["vendors"]:
        target = next((v for v in vendors if v.code == source["code"]), None)
        if not target or any(
            str(getattr(target, key)) != str(value) for key, value in source.items()
        ):
            raise HTTPException(
                409, "Sample procurement was changed. Existing records will not be overwritten."
            )
    for source in catalog["purchase_orders"]:
        target = next((p for p in pos if p.number == source["number"]), None)
        vendor = catalog["vendors"][source["vendor_index"]]
        if (
            not target
            or target.vendor_id != uuid5(workspace.id, vendor["code"])
            or any(
                str(getattr(target, key)) != str(source[key])
                for key in ["currency", "billing_mode", "status", "issued_on", "valid_until"]
            )
            or target.authorized_gross != Decimal(source["authorized_gross"])
        ):
            raise HTTPException(
                409,
                "Sample purchase orders were changed. Existing records will not be overwritten.",
            )
        items = session.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == target.id)
        ).all()
        if len(items) != len(source["items"]) or any(
            any(
                str(getattr(item, k)) != str(value)
                if k in ["sku", "description"]
                else getattr(item, k) != Decimal(str(value))
                for k, value in expected.items()
            )
            for item, expected in zip(
                sorted(items, key=lambda x: x.line_number), source["items"], strict=True
            )
        ):
            raise HTTPException(
                409,
                "Sample purchase order items were changed. Existing records will not be overwritten.",
            )
    installation = SampleInstallation(
        workspace_id=workspace.id, version=VERSION, status="QUEUED", completed=0, run_ids=[]
    )
    session.add(installation)
    audit(
        session,
        workspace.id,
        user.subject,
        "SAMPLE_INITIALIZATION_QUEUED",
        {"version": VERSION, "documents": len(cases())},
    )
    session.flush()
    return installation


def progress(session, workspace_id):
    row = session.get(SampleInstallation, workspace_id)
    if not row:
        return None
    return {
        "status": row.status,
        "completed": row.completed,
        "total": len(cases()),
        "error": row.error,
        "current_run_id": str(row.current_run_id) if row.current_run_id else None,
        "run_ids": row.run_ids,
    }


def advance(factory):
    """Session advisory lock survives ingest's commit. Crash replay uses the same receipt key."""
    with factory() as candidates:
        ids = candidates.scalars(
            select(SampleInstallation.workspace_id)
            .join(Workspace)
            .where(
                SampleInstallation.status.in_(["QUEUED", "PROCESSING"]),
                Workspace.archived_at.is_(None),
            )
        ).all()
    for wid in ids:
        with factory() as lock:
            key = "sample-installation:" + str(wid)
            if not lock.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key,0))"), {"key": key}
            ):
                continue
            try:
                _advance(factory, wid)
            except Exception:
                # Ingest rolls back safely; transient failures remain visible and explicitly resumable.
                with factory.begin() as s:
                    row = s.get(SampleInstallation, wid)
                    if (
                        row.status not in ["QUEUED", "PROCESSING"]
                        or s.get(Workspace, wid).archived_at
                    ):
                        continue
                    row.status = "FAILED"
                    audit(
                        s,
                        wid,
                        "worker",
                        "SAMPLE_INITIALIZATION_FAILED",
                        {"completed": row.completed, "history": "retained"},
                    )
                    row.error = "Sample initialization failed. Check worker/storage availability, then resume. Existing history is retained."
            finally:
                lock.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"), {"key": key}
                )


def _advance(factory, wid):
    with factory() as s:
        financial_lock(s, wid)
        row = s.get(SampleInstallation, wid)
        workspace = s.get(Workspace, wid)
        if row.status not in ["QUEUED", "PROCESSING"] or workspace.archived_at:
            return
        if row.version != VERSION:
            raise RuntimeError("Sample installation version differs; preserve existing history.")
        if row.current_run_id:
            run = s.get(ProcessingRun, row.current_run_id)
            # Follow explicit normal-worker retries, retaining original failure records.
            child = s.scalar(
                select(ProcessingRun)
                .where(ProcessingRun.parent_run_id == run.id)
                .order_by(ProcessingRun.created_at)
                .limit(1)
            )
            if child:
                row.current_run_id = child.id
                s.commit()
                return
            if run.status == "FAILED":
                row.status, row.error = (
                    "FAILED",
                    "Invoice processing failed. Resume sample initialization to retry this invoice; previous evidence stays in history.",
                )
                s.commit()
                return
            if run.status != "SUCCEEDED":
                return
            decision = s.scalar(select(Decision).where(Decision.run_id == run.id))
            if not decision or decision.outcome != cases()[row.completed]["expected"]:
                row.status, row.error = (
                    "FAILED",
                    "A sample outcome differs from the scenario. Inspect the recorded evidence; initialization will not overwrite decisions.",
                )
                s.commit()
                return
            case = cases()[row.completed]
            if (case.get("scan") or case.get("photo")) and not any(
                page["method"] == "OCR" for page in run.pages
            ):
                row.status, row.error = (
                    "FAILED",
                    "Sample OCR evidence is missing. Inspect the recorded stages; decisions will not be overwritten.",
                )
                s.commit()
                return
            row.run_ids = [*row.run_ids, str(run.id)]
            row.completed += 1
            row.current_run_id = None
            s.commit()
        if row.completed == len(cases()):
            verify_balances(s, wid)
            row.status = "COMPLETE"
            row.error = None
            audit(
                s,
                wid,
                "worker",
                "SAMPLE_INITIALIZATION_COMPLETE",
                {"documents": row.completed, "version": row.version},
            )
            s.commit()
            return
        case = cases()[row.completed]
        data = (ROOT / case["file"]).read_bytes()
        receipt = ingest(
            BytesIO(data),
            case["file"],
            VERSION + ":isolated:" + case["file"],
            s,
            wid,
            workspace.owner_subject,
            extraction_mode="FALLBACK",
        )
        row.current_run_id = UUID(receipt["run_id"])
        row.status = "PROCESSING"
        row.error = None
        s.commit()


def resume(session, workspace, user):
    financial_lock(session, workspace.id)
    row = session.get(SampleInstallation, workspace.id)
    if not row or not is_owned_sample(session, workspace, user.subject):
        raise HTTPException(404, "Sample initialization not found.")
    if row.status != "FAILED":
        return row
    if row.current_run_id:
        parent = session.get(ProcessingRun, row.current_run_id)
        if parent.status != "FAILED":
            raise HTTPException(
                409,
                "Inspect the recorded outcome before making further changes. Decisions will not be overwritten.",
            )
        child = session.scalar(
            select(ProcessingRun).where(ProcessingRun.parent_run_id == parent.id).limit(1)
        )
        if not child:
            child = ProcessingRun(
                document_id=parent.document_id,
                parent_run_id=parent.id,
                extraction_mode=parent.extraction_mode,
            )
            session.add(child)
            session.flush()
            session.add(
                RunEvent(
                    run_id=child.id,
                    attempt=0,
                    stage="retry",
                    outcome="QUEUED",
                    detail="Sample initialization resumed; the previous failed run is preserved.",
                )
            )
        row.current_run_id = child.id
    row.status, row.error = "PROCESSING", None
    audit(
        session,
        workspace.id,
        user.subject,
        "SAMPLE_INITIALIZATION_RESUMED",
        {"completed": row.completed},
    )
    return row


def verify_balances(session, wid):
    catalog = catalogue()
    expected = {}
    for case in cases():
        if case["expected"] != "VALIDATED":
            continue
        po = catalog["purchase_orders"][case["po"] - 1]
        item = po["items"][0]
        net = (Decimal(case["q"]) * Decimal(item["unit_price"])).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP
        )
        tax = (net * Decimal(item["tax_rate"])).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        expected[po["number"]] = expected.get(po["number"], Decimal(0)) + net + tax
    for po in session.scalars(select(PurchaseOrder).where(PurchaseOrder.workspace_id == wid)):
        actual = session.scalar(
            select(func.coalesce(func.sum(FinancialCommitment.amount), 0)).where(
                FinancialCommitment.po_id == po.id,
                FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"]),
            )
        )
        if actual != expected.get(po.number, Decimal(0)):
            raise RuntimeError("Sample balances differ from the independent scenario arithmetic.")
