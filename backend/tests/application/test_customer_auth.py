"""Provider-signed identity, first-user provisioning and financial boundary regressions."""

from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select

from app.config import DEMO_WORKSPACE_ID
from app.models import AuditEvent, Membership, Vendor, Workspace
from tests.application import test_security

secure_client = test_security.secure_client

CUSTOMER_A = str(uuid5(NAMESPACE_URL, "test:customer-a"))
CUSTOMER_B = str(uuid5(NAMESPACE_URL, "test:customer-b"))
VIEWER = str(uuid5(NAMESPACE_URL, "test:viewer"))
CACHE_ACCOUNT = str(uuid5(NAMESPACE_URL, "test:cache-account"))


def bootstrap(client, token, subject):
    response = client.post("/api/v1/workspaces/bootstrap", headers=token(subject))
    assert response.status_code == 200, response.text
    return response.json()


def test_new_accounts_are_private_idempotent_and_cannot_choose_another_owner(secure_client):
    client, factory, token = secure_client
    assert client.post("/api/v1/workspaces/bootstrap").status_code == 401
    first = bootstrap(client, token, CUSTOMER_A)
    second = bootstrap(client, token, CUSTOMER_B)
    a, b = first["default_workspace_id"], second["default_workspace_id"]
    assert a != b
    assert len(first["workspaces"]) == len(second["workspaces"]) == 1
    assert first["workspaces"][0]["name"] == "My Workspace"
    assert bootstrap(client, token, CUSTOMER_A) == first
    forged = client.post(
        "/api/v1/workspaces/bootstrap",
        headers={**token(CUSTOMER_B), "X-Workspace-ID": a},
    )
    assert forged.json()["default_workspace_id"] == b
    for route in [
        "vendors",
        "purchase-orders",
        "dashboard",
        "runs",
        "reviews",
        "email",
        "audit-events",
    ]:
        assert (
            client.get(
                "/api/v1/" + route,
                headers={**token(CUSTOMER_B), "X-Workspace-ID": a},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/" + route,
                headers={
                    **token(CUSTOMER_B),
                    "X-Workspace-ID": str(DEMO_WORKSPACE_ID),
                },
            ).status_code
            == 403
        )
    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Vendor)
                .where(Vendor.workspace_id.in_([UUID(a), UUID(b)]))
            )
            == 0
        )
        assert session.get(Workspace, UUID(a)).owner_subject == CUSTOMER_A


def test_isolated_sample_copies_never_copy_gmail_or_share_mutations(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    bootstrap(client, token, CUSTOMER_B)

    def sample(subject):
        response = client.post("/api/v1/workspaces/sample", headers=token(subject))
        assert response.status_code == 201, response.text
        return response.json()["workspace_id"]

    a, b = (
        sample(CUSTOMER_A),
        sample(CUSTOMER_B),
    )
    assert a != b and sample(CUSTOMER_A) == a
    ah = {**token(CUSTOMER_A), "X-Workspace-ID": a}
    bh = {**token(CUSTOMER_B), "X-Workspace-ID": b}
    av = client.get("/api/v1/vendors", headers=ah).json()
    bv = client.get("/api/v1/vendors", headers=bh).json()
    assert len(av) == len(bv) == 18
    assert {v["id"] for v in av}.isdisjoint(v["id"] for v in bv)
    assert len(client.get("/api/v1/purchase-orders", headers=ah).json()) == 36
    assert client.get("/api/v1/dashboard", headers=ah).json()["total_invoices"] == 0
    from app.models import GmailConnection

    with factory() as session:
        assert not session.scalar(
            select(GmailConnection).where(GmailConnection.workspace_id.in_([UUID(a), UUID(b)]))
        )
    assert (
        client.post(
            "/api/v1/vendors",
            headers=ah,
            json={"code": "ONLY-A", "legal_name": "Private supplier", "status": "APPROVED"},
        ).status_code
        == 201
    )
    assert "ONLY-A" not in client.get("/api/v1/vendors", headers=bh).text
    assert (
        client.post(
            "/api/v1/workspaces/" + a + "/archive",
            headers=token(CUSTOMER_B),
            json={"version": 1, "confirm": True},
        ).status_code
        == 403
    )


def test_viewer_cannot_write_even_to_routes_without_reviewer_dependency(secure_client):
    client, factory, token = secure_client
    with factory.begin() as session:
        session.add(
            Membership(
                workspace_id=DEMO_WORKSPACE_ID,
                subject=VIEWER,
                role="VIEWER",
            )
        )
    assert (
        client.post(
            "/api/v1/documents",
            headers=token(VIEWER),
            files={"file": ("invoice.pdf", b"%PDF")},
        ).status_code
        == 403
    )
    assert client.post("/api/v1/email/oauth/start", headers=token(VIEWER)).status_code == 403


def test_recent_activity_allowlist_is_applied_before_limit_and_preserves_raw(secure_client):
    client, factory, token = secure_client
    data = bootstrap(client, token, CUSTOMER_A)
    workspace = UUID(data["default_workspace_id"])
    with factory.begin() as session:
        for action in [
            "EMAIL_CHECK_REQUESTED",
            "EMAIL_CONNECTION",
            "GMAIL_OAUTH_STARTED",
            "SAMPLE_COMPANY_VERIFIED",
            "WORKER_HEARTBEAT",
        ] * 3:
            session.add(
                AuditEvent(workspace_id=workspace, actor="worker", action=action, detail={})
            )
        session.add(
            AuditEvent(
                workspace_id=workspace,
                actor=CUSTOMER_A,
                action="VENDOR_UPDATED",
                detail={"after": {"legal_name": "Real persisted supplier", "code": "SUP-01"}},
            )
        )
        session.add(
            AuditEvent(
                workspace_id=workspace,
                actor="worker",
                action="EMAIL_HANDOFF",
                detail={"outcome": "RUNNING"},
            )
        )
    recent = client.get(
        "/api/v1/audit-events?view=recent&limit=5",
        headers=token(CUSTOMER_A),
    ).json()["events"]
    assert len(recent) == 1
    assert recent[0]["entity"]["vendor"] == "Real persisted supplier"
    assert recent[0]["href"] == "/vendors"
    assert (
        "EMAIL_CHECK_REQUESTED"
        in client.get("/api/v1/audit-events", headers=token(CUSTOMER_A)).text
    )
    assert (
        client.get(
            "/api/v1/audit-events?view=recent",
            headers=token(CUSTOMER_B),
        ).status_code
        == 403
    )


def test_explicit_local_legacy_cleanup_retains_all_historical_records(workflow_db):
    from uuid import NAMESPACE_URL, uuid5

    from app.main import app
    from app.models import Decision, FinancialCommitment, InvoiceDocument, PurchaseOrder
    from scripts.archive_legacy_demo import cleanup
    from tests.application.test_review import client_for, upload

    try:
        with client_for(workflow_db) as client:
            upload(client, workflow_db)
        with workflow_db.begin() as session:
            session.add(
                Workspace(
                    id=uuid5(NAMESPACE_URL, "invoiceguard:asterfield-v1:local-demo-reviewer"),
                    name="Asterfield Retail & Services",
                    owner_subject="local-demo-reviewer",
                )
            )

        def snapshots(session):
            return {
                table.__tablename__: [
                    str(x) for x in session.scalars(select(table.id).order_by(table.id))
                ]
                for table in [InvoiceDocument, Decision, FinancialCommitment, Vendor, PurchaseOrder]
            }

        with workflow_db() as session:
            before = snapshots(session)
            preview = cleanup(session)
            assert preview["preview"] and not preview["archived"]
            result = cleanup(session, confirm=True, version=preview["version"])
            assert result["archived_at"]
            assert snapshots(session) == before
            assert session.scalar(
                select(AuditEvent).where(AuditEvent.action == "WORKSPACE_ARCHIVED")
            )
    finally:
        app.dependency_overrides.clear()


def test_private_api_responses_are_not_cached_after_account_logout(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CACHE_ACCOUNT)
    for path, headers in [
        ("/api/v1/dashboard", token(CACHE_ACCOUNT)),
        ("/api/v1/vendors", {}),
        ("/api/v1/audit-events", token(CACHE_ACCOUNT)),
    ]:
        response = client.get(path, headers=headers)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"
