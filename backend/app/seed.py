"""Add missing synthetic records; preserve existing procurement edits."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import DEMO_WORKSPACE_ID
from app.db import SessionLocal
from app.models import PurchaseOrder, PurchaseOrderItem, Vendor, Workspace

VENDORS = [
    ("SYN-001", "Northstar Office Supplies (Synthetic)", "APPROVED"),
    ("SYN-002", "Harbor IT Services (Synthetic)", "APPROVED"),
    ("SYN-003", "Summit Logistics (Synthetic)", "SUSPENDED"),
]
ORDERS = [
    (
        "PO-2026-001",
        1,
        "USD",
        "ITEMIZED",
        "OPEN",
        "PAPER-A4",
        "A4 paper cartons",
        "100",
        "20",
        "0.10",
    ),
    (
        "PO-2026-002",
        2,
        "USD",
        "AMOUNT_BASED",
        "OPEN",
        "IT-SUPPORT",
        "Annual support, partial billing permitted",
        "12",
        "500",
        "0",
    ),
    (
        "PO-2026-003",
        1,
        "INR",
        "ITEMIZED",
        "CLOSED",
        "CHAIR",
        "Ergonomic office chairs",
        "10",
        "5000",
        "0.18",
    ),
    (
        "PO-2026-004",
        3,
        "USD",
        "AMOUNT_BASED",
        "OPEN",
        "FREIGHT",
        "Freight services",
        "1",
        "1000",
        "0",
    ),
]


def seed(session):
    session.execute(
        insert(Workspace)
        .values(id=DEMO_WORKSPACE_ID, name="Synthetic AP Demo")
        .on_conflict_do_nothing()
    )
    for n, (code, name, status) in enumerate(VENDORS, 1):
        session.execute(
            insert(Vendor)
            .values(
                id=UUID(int=100 + n),
                workspace_id=DEMO_WORKSPACE_ID,
                code=code,
                legal_name=name,
                tax_id=f"SYNTHETIC-TAX-{n}",
                status=status,
            )
            .on_conflict_do_nothing()
        )
    for n, (number, vendor, currency, mode, status, sku, description, qty, price, tax) in enumerate(
        ORDERS, 1
    ):
        gross = Decimal(qty) * Decimal(price) * (1 + Decimal(tax))
        session.execute(
            insert(PurchaseOrder)
            .values(
                id=UUID(int=200 + n),
                workspace_id=DEMO_WORKSPACE_ID,
                vendor_id=UUID(int=100 + vendor),
                number=number,
                currency=currency,
                authorized_gross=gross,
                status=status,
                billing_mode=mode,
                issued_on=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
            )
            .on_conflict_do_nothing()
        )
        po = session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.workspace_id == DEMO_WORKSPACE_ID, PurchaseOrder.number == number
            )
        )
        session.execute(
            insert(PurchaseOrderItem)
            .values(
                id=UUID(int=300 + n),
                po_id=po.id,
                line_number=1,
                sku=sku,
                description=description,
                quantity=Decimal(qty),
                unit_price=Decimal(price),
                tax_rate=Decimal(tax),
            )
            .on_conflict_do_nothing()
        )


if __name__ == "__main__":
    with SessionLocal.begin() as session:
        seed(session)
    print("Synthetic procurement seed complete (existing records preserved).")
