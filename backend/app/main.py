from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import User
from app.config import get_settings
from app.db import get_session
from app.models import AuditEvent, FinancialCommitment, PurchaseOrder, Vendor
from app.operations_api import router as operations_router
from app.review.api import router as review_router
from app.upload_limit import UploadLimit
from app.workflow_api import router


@asynccontextmanager
async def lifespan(app):
    get_settings().validate_runtime()
    yield


app = FastAPI(title="InvoiceGuard AI", version="0.1.0", lifespan=lifespan)


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    legal_name: str
    status: str


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_number: int
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal


class POOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    currency: str
    authorized_gross: Decimal
    status: str
    billing_mode: str
    issued_on: date
    valid_until: date
    vendor: VendorOut
    items: list[ItemOut]
    reserved_gross: Decimal
    settled_gross: Decimal
    available_gross: Decimal


@app.get("/api/v1/health/live")
def live():
    return {"status": "ok", "mode": get_settings().app_environment}


@app.get("/api/v1/health/ready")
def ready(session: Annotated[Session, Depends(get_session)]):
    try:
        session.execute(text("SELECT 1"))
        session.execute(select(PurchaseOrder.id).limit(1))
        session.execute(select(AuditEvent.id).limit(1))
        return {"status": "ready", "database": "connected"}
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable_or_unmigrated"},
        )


@app.get("/api/v1/vendors", response_model=list[VendorOut])
def vendors(session: Annotated[Session, Depends(get_session)], user: User):
    return session.scalars(
        select(Vendor).where(Vendor.workspace_id == user.workspace_id).order_by(Vendor.code)
    ).all()


@app.get("/api/v1/purchase-orders", response_model=list[POOut])
def purchase_orders(session: Annotated[Session, Depends(get_session)], user: User):
    orders = session.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.workspace_id == user.workspace_id)
        .options(selectinload(PurchaseOrder.vendor), selectinload(PurchaseOrder.items))
        .order_by(PurchaseOrder.number)
    ).all()
    totals = session.execute(
        select(
            FinancialCommitment.po_id,
            FinancialCommitment.status,
            func.sum(FinancialCommitment.amount),
        )
        .join(PurchaseOrder)
        .where(PurchaseOrder.workspace_id == user.workspace_id)
        .group_by(FinancialCommitment.po_id, FinancialCommitment.status)
    ).all()
    for po in orders:
        po.reserved_gross = sum(
            (
                amount
                for po_id, status, amount in totals
                if po_id == po.id and status in ["RESERVED", "HELD"]
            ),
            Decimal(0),
        )
        po.settled_gross = sum(
            (amount for po_id, status, amount in totals if po_id == po.id and status == "SETTLED"),
            Decimal(0),
        )
        po.available_gross = po.authorized_gross - po.reserved_gross - po.settled_gross
    return orders


app.add_middleware(UploadLimit)
app.include_router(router)

app.include_router(review_router)
app.include_router(operations_router)


@app.get("/api/v1/config")
def public_config():
    s = get_settings()
    return {
        "auth_mode": s.auth_mode,
        "issuer": s.oidc_issuer,
        "audience": s.oidc_audience,
        "client_id": s.oidc_client_id,
        "synthetic_data": True,
    }


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database temporarily unavailable. Your submitted work is retained; retry after service recovery."
        },
    )


# The deployment image serves the compiled React application from the API origin.


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API route not found.")
    root = get_settings().frontend_dist.resolve()
    requested = (root / path).resolve()
    if not requested.is_relative_to(root):
        raise HTTPException(404, "Not found.")
    if requested.is_file():
        return FileResponse(requested, headers={"X-Content-Type-Options": "nosniff"})
    if path and "." in path.rsplit("/", 1)[-1]:
        raise HTTPException(404, "Asset not found.")
    if (root / "index.html").is_file():
        return FileResponse(
            root / "index.html",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )
    raise HTTPException(404, "Frontend build not found. Build the React application first.")
