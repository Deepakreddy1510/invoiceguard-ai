"""Workspace discovery and add-only provisioning. Never resets financial history."""

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.audit import audit
from app.config import get_settings
from app.models import Membership, PurchaseOrder, PurchaseOrderItem, Vendor, Workspace

EXPANDED_DEMO = uuid5(NAMESPACE_URL, "invoiceguard-complete-synthetic-demo")


def local_ids(session, subject):
    settings = get_settings()
    owned = session.scalars(select(Workspace.id).where(Workspace.owner_subject == subject)).all()
    return set(owned) | {settings.local_workspace_id, EXPANDED_DEMO}


def accessible(session, user):
    if get_settings().auth_mode == "local":
        records = session.scalars(
            select(Workspace)
            .where(Workspace.id.in_(local_ids(session, user.subject)))
            .order_by(Workspace.created_at.desc())
        ).all()
        return [(workspace, "ADMIN") for workspace in records]
    return session.execute(
        select(Workspace, Membership.role)
        .join(Membership)
        .where(Membership.subject == user.subject)
        .order_by(Workspace.created_at.desc())
    ).all()


def workspace_kind(workspace):
    return (
        "DEMO"
        if workspace.id == EXPANDED_DEMO or workspace.name == "Synthetic AP Demo"
        else workspace.kind
    )


def provision_my(session, user):
    workspace_id = uuid5(NAMESPACE_URL, "invoiceguard:my:" + user.subject)
    created = session.scalar(
        insert(Workspace)
        .values(id=workspace_id, name="My Workspace", kind="MY", owner_subject=user.subject)
        .on_conflict_do_nothing()
        .returning(Workspace.id)
    )
    session.execute(
        insert(Membership)
        .values(workspace_id=workspace_id, subject=user.subject, role="ADMIN")
        .on_conflict_do_nothing(index_elements=["workspace_id", "subject"])
    )
    if created:
        audit(session, workspace_id, user.subject, "WORKSPACE_CREATED", {"kind": "MY"})
    return session.get(Workspace, workspace_id)


def seed_public(session, workspace_id):
    catalogue = json.loads((Path(__file__).parents[1] / "demo/procurement.json").read_text())

    def mapped(source):
        return uuid5(workspace_id, source)

    for vendor in catalogue["vendors"]:
        session.execute(
            insert(Vendor)
            .values(
                id=mapped(vendor["id"]),
                workspace_id=workspace_id,
                code=vendor["code"],
                legal_name=vendor["legal_name"],
                tax_id=vendor["tax_id"],
                status=vendor["status"],
            )
            .on_conflict_do_nothing()
        )
    for po in catalogue["purchase_orders"]:
        session.execute(
            insert(PurchaseOrder)
            .values(
                id=mapped(po["id"]),
                workspace_id=workspace_id,
                vendor_id=mapped(po["vendor_id"]),
                number=po["number"],
                currency=po["currency"],
                authorized_gross=Decimal(po["authorized_gross"]),
                status=po["status"],
                billing_mode=po["billing_mode"],
                issued_on=date.fromisoformat(po["issued_on"]),
                valid_until=date.fromisoformat(po["valid_until"]),
            )
            .on_conflict_do_nothing()
        )
        for item in po["items"]:
            session.execute(
                insert(PurchaseOrderItem)
                .values(
                    id=mapped(item["id"]),
                    po_id=mapped(po["id"]),
                    line_number=item["line_number"],
                    sku=item["sku"],
                    description=item["description"],
                    quantity=Decimal(item["quantity"]),
                    unit_price=Decimal(item["unit_price"]),
                    tax_rate=Decimal(item["tax_rate"]),
                )
                .on_conflict_do_nothing()
            )
    return catalogue


def fresh_demo(session, user, request_id: UUID):
    # User/request-scoped deterministic ID makes reconnect/retry safe.
    from app.ingestion import ingest
    from scripts.seed_workspace import document

    workspace_id = uuid5(
        NAMESPACE_URL, "invoiceguard:fresh:" + user.subject + ":" + str(request_id)
    )
    created = session.scalar(
        insert(Workspace)
        .values(id=workspace_id, name="Demo Workspace", kind="DEMO", owner_subject=user.subject)
        .on_conflict_do_nothing()
        .returning(Workspace.id)
    )
    workspace = session.get(Workspace, workspace_id)
    if workspace.owner_subject != user.subject or workspace.kind != "DEMO":
        raise ValueError("Workspace ownership conflict.")
    session.execute(
        insert(Membership)
        .values(workspace_id=workspace_id, subject=user.subject, role="ADMIN")
        .on_conflict_do_nothing(index_elements=["workspace_id", "subject"])
    )
    catalogue = seed_public(session, workspace_id)
    if created:
        audit(
            session,
            workspace_id,
            user.subject,
            "FRESH_DEMO_CREATED",
            {
                "previous_workspace_id": str(user.workspace_id),
                "vendors": 18,
                "purchase_orders": 36,
                "history_reset": False,
            },
        )
    session.commit()
    vendors = {v["id"]: v for v in catalogue["vendors"]}
    scenarios = [
        (po, "BASELINE-" + po["number"], "2", {})
        for po in catalogue["purchase_orders"]
        if po["status"] == "PARTIALLY_BILLED"
    ]
    paper, services = catalogue["purchase_orders"][:2]
    scenarios += [
        (paper, "DEMO-VALID-001", "5", {}),
        (paper, "DEMO-VALID-001", "5", {"copy": True}),
        (paper, "DEMO-MISSING-001", "3", {"missing": True}),
        (paper, "DEMO-OVER-001", "200", {}),
        (paper, "DEMO-SCAN-001", "4", {"scanned": True}),
    ]
    scenarios += [
        (services, "DEMO-PARTIAL-" + str(index), quantity, {})
        for index, quantity in enumerate(["2", "3", "8"], 1)
    ]
    for index, (po, number, quantity, flags) in enumerate(scenarios):
        payload = document(po, vendors[po["vendor_id"]], number, quantity, **flags)
        ingest(
            BytesIO(payload),
            number + ".pdf",
            "fresh:" + str(request_id) + ":" + str(index),
            session,
            workspace_id,
            user.subject,
            extraction_mode="FALLBACK",
        )
    return {
        "workspace_id": str(workspace_id),
        "queued_submissions": len(scenarios),
        "replayed": not bool(created),
    }
