"""Creation preserves verified ownership, financial isolation and idempotence."""

from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models import (
    AuditEvent,
    FinancialCommitment,
    GmailConnection,
    InvoiceDocument,
    Membership,
    PurchaseOrder,
    SampleInstallation,
    Vendor,
    Workspace,
)
from tests.application import test_security
from tests.application.test_customer_auth import CUSTOMER_A, CUSTOMER_B, bootstrap
from tests.application.test_sample_initialization import drain

secure_client = test_security.secure_client


def test_named_workspaces_and_retries(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    bootstrap(client, token, CUSTOMER_B)
    payload = {"request_id": str(uuid4()), "name": "Nandi Pipes", "workspace_type": "EMPTY"}
    assert client.post("/api/v1/workspaces", json=payload).status_code == 401
    first = client.post("/api/v1/workspaces", headers=token(CUSTOMER_A), json=payload)
    assert first.status_code == 201, first.text
    wid = first.json()["workspace_id"]
    replay = client.post("/api/v1/workspaces", headers=token(CUSTOMER_A), json=payload)
    assert replay.json()["workspace_id"] == wid and replay.json()["replayed"]
    assert (
        client.post(
            "/api/v1/workspaces", headers=token(CUSTOMER_A), json={**payload, "name": "Other"}
        ).status_code
        == 409
    )
    with factory() as s:
        workspace = s.get(Workspace, UUID(wid))
        assert workspace.kind == "CUSTOM" and workspace.name == "Nandi Pipes"
        assert workspace.owner_subject == CUSTOMER_A
        assert (
            s.scalar(select(Membership.role).where(Membership.workspace_id == UUID(wid))) == "ADMIN"
        )
        for model in [Vendor, PurchaseOrder, InvoiceDocument, GmailConnection]:
            assert (
                s.scalar(
                    select(func.count()).select_from(model).where(model.workspace_id == UUID(wid))
                )
                == 0
            )
        assert (
            s.scalar(
                select(func.count())
                .select_from(FinancialCommitment)
                .join(PurchaseOrder)
                .where(PurchaseOrder.workspace_id == UUID(wid))
            )
            == 0
        )
    sample_payload = {**payload, "request_id": str(uuid4()), "workspace_type": "SAMPLE"}
    result = client.post("/api/v1/workspaces", headers=token(CUSTOMER_A), json=sample_payload)
    assert result.status_code == 201, result.text
    sample = result.json()["workspace_id"]
    assert sample != wid
    for target in [sample, wid]:
        for route in [
            "vendors",
            "purchase-orders",
            "runs",
            "dashboard",
            "email",
            "audit-events",
            "workspaces/sample-initialization",
        ]:
            assert (
                client.get(
                    "/api/v1/" + route, headers={**token(CUSTOMER_B), "X-Workspace-ID": target}
                ).status_code
                == 403
            )
    drain(factory, UUID(sample))
    with factory() as s:
        assert s.get(SampleInstallation, UUID(sample)).completed == 21
        assert not s.scalar(
            select(InvoiceDocument.id).where(InvoiceDocument.workspace_id == UUID(wid))
        )
        assert not s.scalar(
            select(GmailConnection.id).where(GmailConnection.workspace_id == UUID(sample))
        )
    assert (
        client.patch(
            "/api/v1/workspaces/" + sample,
            headers=token(CUSTOMER_A),
            json={"version": 1, "name": "Renamed sample"},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/workspaces", headers=token(CUSTOMER_A), json=sample_payload).json()[
        "replayed"
    ]
    with factory() as s:
        assert s.get(Workspace, UUID(sample)).name == "Renamed sample"
        assert s.get(Workspace, UUID(sample)).kind == "DEMO"
        assert (
            s.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.workspace_id == UUID(sample),
                    AuditEvent.action == "WORKSPACE_CREATED",
                )
            )
            == 1
        )


def test_creation_validation_and_role(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    payload = {"request_id": str(uuid4()), "name": "Valid", "workspace_type": "EMPTY"}
    for changes in [
        {"name": " "},
        {"name": "a" * 161},
        {"name": "a\nb"},
        {"name": "a\u200bb"},
        {"workspace_type": "CUSTOM"},
        {"owner_subject": CUSTOMER_B},
        {"role": "ADMIN"},
    ]:
        assert (
            client.post(
                "/api/v1/workspaces", headers=token(CUSTOMER_A), json={**payload, **changes}
            ).status_code
            == 422
        )
    with factory.begin() as s:
        s.scalar(select(Membership).where(Membership.subject == CUSTOMER_A)).role = "VIEWER"
    assert (
        client.post("/api/v1/workspaces", headers=token(CUSTOMER_A), json=payload).status_code
        == 403
    )
