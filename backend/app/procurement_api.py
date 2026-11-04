from uuid import UUID

from fastapi import APIRouter, Query

from app.audit import audit, financial_lock
from app.auth import Reviewer, User
from app.procurement import (
    Cancellation,
    POInput,
    POUpdate,
    VendorInput,
    VendorUpdate,
    check_version,
    create_po,
    create_vendor,
    delete_po,
    delete_vendor,
    po_for,
    update_po,
    update_vendor,
    vendor_for,
    vendor_view,
)
from app.workflow_api import DB

router = APIRouter(prefix="/api/v1")


@router.get("/vendors/{vendor_id}")
def vendor_detail(vendor_id: UUID, session: DB, user: User):
    return vendor_view(session, vendor_for(session, user, vendor_id))


@router.post("/vendors", status_code=201)
def add_vendor(payload: VendorInput, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    vendor = create_vendor(session, user, payload)
    result = vendor_view(session, vendor)
    session.commit()
    return result


@router.put("/vendors/{vendor_id}")
def edit_vendor(vendor_id: UUID, payload: VendorUpdate, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    vendor = update_vendor(session, user, vendor_for(session, user, vendor_id), payload)
    result = vendor_view(session, vendor)
    session.commit()
    return result


@router.delete("/vendors/{vendor_id}")
def remove_vendor(vendor_id: UUID, session: DB, user: Reviewer, version: int = Query(ge=1)):
    financial_lock(session, user.workspace_id)
    delete_vendor(session, user, vendor_for(session, user, vendor_id), version)
    session.commit()
    return {"deleted": True}


@router.post("/purchase-orders", status_code=201)
def add_po(payload: POInput, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    po = create_po(session, user, payload)
    result = {"id": str(po.id), "number": po.number, "version": po.version}
    session.commit()
    return result


@router.put("/purchase-orders/{po_id}")
def edit_po(po_id: UUID, payload: POUpdate, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    po = update_po(session, user, po_for(session, user, po_id), payload)
    result = {"id": str(po.id), "number": po.number, "version": po.version}
    session.commit()
    return result


@router.post("/purchase-orders/{po_id}/cancel")
def cancel_po(po_id: UUID, payload: Cancellation, session: DB, user: Reviewer):
    financial_lock(session, user.workspace_id)
    po = po_for(session, user, po_id)
    check_version(po, payload.version)
    before = po.status
    po.status = "CANCELLED"
    po.version += 1
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PURCHASE_ORDER_CANCELLED",
        {
            "po_id": str(po.id),
            "previous_status": before,
            "reason": payload.reason,
            "commitments_released": False,
        },
    )
    session.commit()
    return {"id": str(po.id), "status": po.status, "version": po.version}


@router.delete("/purchase-orders/{po_id}")
def remove_po(po_id: UUID, session: DB, user: Reviewer, version: int = Query(ge=1)):
    financial_lock(session, user.workspace_id)
    delete_po(session, user, po_for(session, user, po_id), version)
    session.commit()
    return {"deleted": True}
