from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import DEMO_WORKSPACE_ID
from app.db import get_session
from app.main import app
from app.models import PurchaseOrder, PurchaseOrderItem, Vendor, Workspace
from app.seed import seed


def test_seed_is_repeatable_and_preserves_edits(session):
    seed(session)
    vendor = session.scalar(select(Vendor).where(Vendor.code == "SYN-001"))
    vendor.legal_name = "Reviewer-maintained name"
    session.flush()
    seed(session)
    assert session.scalar(select(func.count()).select_from(Vendor)) == 3
    assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 4
    assert session.scalar(select(func.count()).select_from(PurchaseOrderItem)) == 4
    session.refresh(vendor)
    assert vendor.legal_name == "Reviewer-maintained name"
    orders = session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.number)).all()
    assert [po.authorized_gross for po in orders] == [
        Decimal(2200),
        Decimal(6000),
        Decimal(59000),
        Decimal(1000),
    ]
    for po in orders:
        assert po.authorized_gross == sum(
            i.quantity * i.unit_price * (1 + i.tax_rate) for i in po.items
        )


def test_api_reads_database_and_scopes_workspace(client, session):
    seed(session)
    other = uuid4()
    session.add(Workspace(id=other, name="Private other workspace"))
    session.flush()
    session.add(
        Vendor(workspace_id=other, code="PRIVATE", legal_name="Not visible", status="APPROVED")
    )
    session.flush()
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"
    vendors = client.get("/api/v1/vendors").json()
    assert len(vendors) == 3
    assert all(v["code"] != "PRIVATE" for v in vendors)
    response = client.get("/api/v1/purchase-orders")
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 4
    assert orders[0]["authorized_gross"] == "2200.000000"
    assert orders[0]["items"][0]["quantity"] == "100.000000"
    assert orders[3]["vendor"]["status"] == "SUSPENDED"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE purchase_orders SET authorized_gross = -1",
        "UPDATE purchase_orders SET currency = 'usd'",
        "UPDATE purchase_orders SET status = 'UNKNOWN'",
        "UPDATE purchase_orders SET valid_until = '2025-01-01'",
        "UPDATE purchase_order_items SET quantity = 0",
        "UPDATE purchase_order_items SET tax_rate = 2",
        "UPDATE vendors SET status = 'UNKNOWN'",
        "UPDATE purchase_orders SET number = 'SAME'",
    ],
)
def test_database_rejects_invalid_procurement(session, sql):
    seed(session)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text(sql))


def test_database_prevents_cross_workspace_vendor_link(session):
    seed(session)
    other = uuid4()
    session.add(Workspace(id=other, name="Other"))
    session.flush()
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text("UPDATE purchase_orders SET workspace_id = :other"), {"other": other})


def test_rollback_leaves_no_vendor(session):
    seed(session)
    with session.begin_nested() as transaction:
        session.add(
            Vendor(
                workspace_id=DEMO_WORKSPACE_ID,
                code="ROLLBACK",
                legal_name="Temporary",
                status="APPROVED",
            )
        )
        session.flush()
        transaction.rollback()
    assert session.scalar(select(Vendor).where(Vendor.code == "ROLLBACK")) is None


def test_readiness_reports_database_failure_without_details():
    class BrokenSession:
        def execute(self, *args):
            raise OperationalError("sensitive connection", {}, Exception("secret"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 503
            assert "secret" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_hosted_mode_refused_until_authentication_exists(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="local-only"), TestClient(app):
            pass
    finally:
        get_settings.cache_clear()
