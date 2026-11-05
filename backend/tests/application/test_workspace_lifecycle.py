"""Lifecycle controls pause new work while retaining the real financial ledger."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.config import DEMO_WORKSPACE_ID
from app.main import app
from app.models import Decision, FinancialCommitment, Membership, ProcessingRun, Workspace
from app.worker.main import claim, run_once
from tests.application import test_gmail, test_security
from tests.application.test_review import client_for, upload

secure_client = test_security.secure_client
mailbox = test_gmail.mailbox
gmail_env = test_gmail.gmail_env


def spaces(client):
    return client.post("/api/v1/workspaces/bootstrap").json()["workspaces"]


def rename(client, w, name, headers=None):
    return client.patch(
        "/api/v1/workspaces/" + w["id"],
        headers=headers,
        json={"name": name, "version": w["version"]},
    )


def lifecycle(client, w, action, headers=None):
    return client.post(
        "/api/v1/workspaces/" + w["id"] + "/" + action,
        headers=headers,
        json={"version": w["version"], "confirm": True},
    )


def test_rename_is_persisted_and_version_checked(workflow_db):
    try:
        with client_for(workflow_db) as client:
            target = next(w for w in spaces(client) if w["kind"] == "MY")
            response = rename(client, target, "Cedarline Finance")
            assert response.status_code == 200, response.text
            assert response.json()["id"] == target["id"] and response.json()["version"] == 2
            assert rename(client, target, "Stale overwrite").status_code == 409
            assert (
                next(w for w in spaces(client) if w["id"] == target["id"])["name"]
                == "Cedarline Finance"
            )
            assert (
                client.get("/api/v1/me", headers={"X-Workspace-ID": target["id"]}).json()[
                    "workspace_name"
                ]
                == "Cedarline Finance"
            )
            assert (
                client.get("/api/v1/audit-events", headers={"X-Workspace-ID": target["id"]}).json()[
                    "events"
                ][0]["action"]
                == "WORKSPACE_RENAMED"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("name", ["", "   ", "Bad\nName", "x" * 161])
def test_invalid_workspace_names_do_not_mutate(client, session, name):
    from app.seed import seed

    seed(session)
    target = next(w for w in spaces(client) if w["kind"] == "MY")
    assert rename(client, target, name).status_code == 422


def test_archive_blocks_mutations_hides_selection_and_restores(workflow_db):
    try:
        with client_for(workflow_db) as client:
            target = next(w for w in spaces(client) if w["kind"] == "MY")
            headers = {"X-Workspace-ID": target["id"]}
            archived = lifecycle(client, target, "archive")
            assert archived.status_code == 200, archived.text
            assert target["id"] not in [w["id"] for w in spaces(client)]
            assert next(
                w
                for w in client.get("/api/v1/workspaces?include_archived=true").json()["workspaces"]
                if w["id"] == target["id"]
            )["archived_at"]
            assert client.get("/api/v1/vendors", headers=headers).status_code == 200
            assert (
                client.post(
                    "/api/v1/vendors",
                    headers=headers,
                    json={"code": "A", "legal_name": "Retained Supplier", "status": "APPROVED"},
                ).status_code
                == 409
            )
            assert client.post("/api/v1/email/oauth/start", headers=headers).status_code == 409
            target.update(archived.json())
            restored = lifecycle(client, target, "restore")
            assert restored.status_code == 200, restored.text
            assert restored.json()["archived_at"] is None
            assert target["id"] in [w["id"] for w in spaces(client)]
            assert (
                client.post(
                    "/api/v1/vendors",
                    headers=headers,
                    json={"code": "A", "legal_name": "Restored Supplier", "status": "APPROVED"},
                ).status_code
                == 201
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["VIEWER", "REVIEWER"])
def test_workspace_changes_require_target_administrator(secure_client, role):
    client, factory, token = secure_client
    with factory.begin() as session:
        session.add(Membership(workspace_id=DEMO_WORKSPACE_ID, subject="invited-user", role=role))
    target = {"id": str(DEMO_WORKSPACE_ID), "version": 1}
    for response in [
        rename(client, target, "Forbidden rename", token()),
        lifecycle(client, target, "archive", token()),
        lifecycle(client, target, "restore", token()),
    ]:
        assert response.status_code == 403
    assert client.get("/api/v1/vendors", headers=token()).status_code == 200


def test_unrelated_admin_cannot_manage_another_workspace(secure_client):
    client, factory, token = secure_client
    from uuid import uuid4

    with factory.begin() as session:
        own = Workspace(id=uuid4(), name="Own finance workspace", owner_subject="invited-user")
        session.add(own)
        session.flush()
        session.add(Membership(workspace_id=own.id, subject="invited-user", role="ADMIN"))
        session.add(Membership(workspace_id=DEMO_WORKSPACE_ID, subject="other-admin", role="ADMIN"))
    assert (
        rename(
            client,
            {"id": str(DEMO_WORKSPACE_ID), "version": 1},
            "Unauthorized",
            token("invited-user"),
        ).status_code
        == 403
    )


def test_queued_work_pauses_and_real_commitments_survive_archive(workflow_db):
    try:
        with client_for(workflow_db) as client:
            spaces(client)
            original = upload(
                client,
                workflow_db,
                number="ARCHIVE-HISTORY",
                quantity="3",
                subtotal="60",
                tax="6",
                total="66",
            )
            queued = client.post(
                "/api/v1/documents",
                files={
                    "file": (
                        "queued.pdf",
                        test_gmail.invoice_pdf(number="ARCHIVE-QUEUED"),
                        "application/pdf",
                    )
                },
            )
            assert queued.status_code == 202, queued.text
            target = next(w for w in spaces(client) if w["id"] == str(DEMO_WORKSPACE_ID))
            with workflow_db() as session:
                ledger = [
                    (str(c.id), str(c.amount), c.status)
                    for c in session.scalars(select(FinancialCommitment)).all()
                ]
                decisions = session.scalar(select(func.count()).select_from(Decision))
            archived = lifecycle(client, target, "archive")
            assert archived.status_code == 200, archived.text
            assert claim(workflow_db, UUID(queued.json()["run_id"])) is None
            assert client.post("/api/v1/runs/" + original["id"] + "/review").status_code == 409
            assert client.get("/api/v1/runs/" + original["id"]).json()["outcome"] == "VALIDATED"
            with workflow_db() as session:
                assert ledger == [
                    (str(c.id), str(c.amount), c.status)
                    for c in session.scalars(select(FinancialCommitment)).all()
                ]
                assert decisions == session.scalar(select(func.count()).select_from(Decision))
                assert session.get(ProcessingRun, UUID(queued.json()["run_id"])).status == "QUEUED"
            target.update(archived.json())
            assert lifecycle(client, target, "restore").status_code == 200
            assert run_once(workflow_db, run_id=UUID(queued.json()["run_id"]))
    finally:
        app.dependency_overrides.clear()


def test_archive_refuses_an_active_invoice_lease(workflow_db):
    try:
        with client_for(workflow_db) as client:
            spaces(client)
            receipt = client.post(
                "/api/v1/documents",
                files={"file": ("pending.pdf", test_gmail.invoice_pdf(), "application/pdf")},
            ).json()
            job = claim(workflow_db, UUID(receipt["run_id"]))
            assert job
            target = next(w for w in spaces(client) if w["id"] == str(DEMO_WORKSPACE_ID))
            response = lifecycle(client, target, "archive")
            assert response.status_code == 409 and "processing" in response.text
            with workflow_db() as session:
                assert session.get(Workspace, DEMO_WORKSPACE_ID).archived_at is None
    finally:
        app.dependency_overrides.clear()


def test_archived_gmail_does_not_poll_and_restore_resumes(mailbox):
    from app.email_intake.service import sync_connection

    target = next(w for w in spaces(mailbox.client) if w["id"] == str(DEMO_WORKSPACE_ID))
    archived = lifecycle(mailbox.client, target, "archive")
    assert archived.status_code == 200, archived.text
    calls = list(mailbox.calls)
    assert sync_connection(mailbox.factory, mailbox.connection_id) is False
    assert mailbox.calls == calls
    test_gmail.add_message(mailbox)
    target.update(archived.json())
    assert lifecycle(mailbox.client, target, "restore").status_code == 200
    assert test_gmail.sync(mailbox)


def test_business_feed_omits_routine_mail_checks_but_keeps_audit(session, client):
    from app.audit import audit
    from app.seed import seed

    seed(session)
    for action in [
        "EMAIL_SYNC",
        "EMAIL_CHECKPOINT_RECOVERY",
        "EMAIL_ATTACHMENT_FETCH",
        "EMAIL_DISCOVERY",
    ]:
        audit(session, DEMO_WORKSPACE_ID, "gmail-worker", action, {"outcome": "SUCCEEDED"})
    audit(session, DEMO_WORKSPACE_ID, "gmail-worker", "EMAIL_HANDOFF", {"outcome": "SUCCEEDED"})
    session.flush()
    business = client.get("/api/v1/audit-events?view=business").json()["events"]
    assert [e["action"] for e in business] == ["EMAIL_HANDOFF"]
    assert len(client.get("/api/v1/audit-events").json()["events"]) == 5


def test_archive_does_not_interrupt_a_live_mailbox_lock(mailbox):
    from app.email_intake.service import exclusive

    target = next(w for w in spaces(mailbox.client) if w["id"] == str(DEMO_WORKSPACE_ID))
    with exclusive(mailbox.factory, mailbox.connection_id) as acquired:
        assert acquired
        response = lifecycle(mailbox.client, target, "archive")
        assert response.status_code == 409 and "email check" in response.text
    assert lifecycle(mailbox.client, target, "archive").status_code == 200


def test_concurrent_workspace_names_do_not_lose_updates(workflow_db):
    from concurrent.futures import ThreadPoolExecutor

    try:
        with client_for(workflow_db) as client:
            target = next(w for w in spaces(client) if w["kind"] == "MY")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda name: rename(client, target, name),
                        ["Finance North", "Finance South"],
                    )
                )
            assert sorted(r.status_code for r in results) == [200, 409]
            updated = next(w for w in spaces(client) if w["id"] == target["id"])
            assert updated["version"] == 2 and updated["name"] in ["Finance North", "Finance South"]
    finally:
        app.dependency_overrides.clear()


def test_renaming_a_legacy_demo_preserves_honest_demo_classification(workflow_db):
    try:
        with client_for(workflow_db) as client:
            target = next(w for w in spaces(client) if w["id"] == str(DEMO_WORKSPACE_ID))
            assert target["kind"] == "DEMO"
            assert rename(client, target, "Finance Team Sample").status_code == 200
            updated = next(w for w in spaces(client) if w["id"] == target["id"])
            assert updated["kind"] == "DEMO" and updated["name"] == "Finance Team Sample"
            assert len(client.get("/api/v1/vendors").json()) == 3
            assert len(client.get("/api/v1/purchase-orders").json()) == 4
    finally:
        app.dependency_overrides.clear()


def test_last_active_workspace_cannot_be_archived_until_another_is_restored(workflow_db):
    try:
        with client_for(workflow_db) as client:
            records = spaces(client)
            mine = next(w for w in records if w["kind"] == "MY")
            demo = next(w for w in records if w["id"] == str(DEMO_WORKSPACE_ID))
            archived = lifecycle(client, mine, "archive")
            assert archived.status_code == 200
            response = lifecycle(client, demo, "archive")
            assert response.status_code == 409 and "one active workspace" in response.text
            mine.update(archived.json())
            assert lifecycle(client, mine, "restore").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_archival_stops_mail_reads_without_preventing_queued_token_revocation(mailbox):
    from app.email_intake.service import mail_once
    from app.models import GmailConnection

    target = next(w for w in spaces(mailbox.client) if w["id"] == str(DEMO_WORKSPACE_ID))
    assert (
        mailbox.client.post(
            "/api/v1/email/connections/" + str(mailbox.connection_id) + "/disconnect"
        ).status_code
        == 202
    )
    assert lifecycle(mailbox.client, target, "archive").status_code == 200
    before = len(mailbox.calls)
    assert mail_once(mailbox.factory)
    calls = mailbox.calls[before:]
    assert calls and all(request.url.path == "/revoke" for request in calls)
    with mailbox.factory() as session:
        connection = session.get(GmailConnection, mailbox.connection_id)
        assert connection.status == "DISCONNECTED" and connection.credentials is None
