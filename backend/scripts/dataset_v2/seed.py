from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import PurchaseOrder, PurchaseOrderItem, Vendor, Workspace
from scripts.dataset_v2.common import WORKSPACE


def seed_catalogue(engine, cat):
    # Caller must have created an empty, owned evaluation database. No upserts/reset.
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=UUID(WORKSPACE), name="Synthetic v2 isolated evaluation"))
        session.flush()
        for v in cat["vendors"]:
            session.add(
                Vendor(
                    id=UUID(v["id"]),
                    workspace_id=UUID(WORKSPACE),
                    code=v["code"],
                    legal_name=v["legal_name"],
                    tax_id=v["tax_id"],
                    status=v["status"],
                )
            )
        session.flush()
        for p in cat["purchase_orders"]:
            session.add(
                PurchaseOrder(
                    id=UUID(p["id"]),
                    workspace_id=UUID(WORKSPACE),
                    vendor_id=UUID(p["vendor_id"]),
                    number=p["number"],
                    currency=p["currency"],
                    authorized_gross=Decimal(p["authorized_gross"]),
                    status=p["status"],
                    billing_mode=p["billing_mode"],
                    issued_on=date.fromisoformat(p["issued_on"]),
                    valid_until=date.fromisoformat(p["valid_until"]),
                )
            )
        session.flush()
        for p in cat["purchase_orders"]:
            for i in p["items"]:
                session.add(
                    PurchaseOrderItem(
                        id=UUID(i["id"]),
                        po_id=UUID(p["id"]),
                        line_number=i["line_number"],
                        sku=i["sku"],
                        description=i["description"],
                        quantity=Decimal(i["quantity"]),
                        unit_price=Decimal(i["unit_price"]),
                        tax_rate=Decimal(i["tax_rate"]),
                    )
                )
