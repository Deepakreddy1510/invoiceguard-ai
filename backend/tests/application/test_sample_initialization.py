"""Private samples use real PDFs, deterministic financial ordering and durable retries."""

from collections import Counter
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import func, select

from app.models import (
    Decision,
    FinancialCommitment,
    GmailConnection,
    InvoiceDocument,
    ProcessingRun,
    PurchaseOrder,
    RunEvent,
    SampleInstallation,
    Vendor,
)
from app.sample_service import advance, sample_id
from app.worker.main import run_once
from app.workspace_service import provision_sample
from tests.application import test_security
from tests.application.test_customer_auth import CUSTOMER_A, CUSTOMER_B, bootstrap

secure_client = test_security.secure_client


def create(client, token, subject=CUSTOMER_A):
    bootstrap(client, token, subject)
    response = client.post("/api/v1/workspaces/sample", headers=token(subject))
    assert response.status_code == 201, response.text
    wid = response.json()["workspace_id"]
    return UUID(wid), {**token(subject), "X-Workspace-ID": wid}


def drain(factory, wid):
    for _ in range(60):
        with factory() as s:
            row = s.get(SampleInstallation, wid)
            if row.status == "COMPLETE":
                return
            assert row.status != "FAILED", row.error
        run_once(factory)
    raise AssertionError("Sample did not finish")


def counts(s, wid):
    return (
        s.scalar(
            select(func.count())
            .select_from(InvoiceDocument)
            .where(InvoiceDocument.workspace_id == wid)
        ),
        s.scalar(
            select(func.count())
            .select_from(ProcessingRun)
            .join(InvoiceDocument)
            .where(InvoiceDocument.workspace_id == wid)
        ),
        s.scalar(
            select(func.sum(FinancialCommitment.amount))
            .join(PurchaseOrder)
            .where(PurchaseOrder.workspace_id == wid)
        ),
    )


def test_real_history_order_evidence_balances_isolation_and_idempotence(secure_client):
    client, factory, token = secure_client
    wid, headers = create(client, token)
    bootstrap(client, token, CUSTOMER_B)
    assert (
        client.post(
            "/api/v1/vendors",
            headers=headers,
            json={"code": "X", "legal_name": "X", "status": "APPROVED"},
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/api/v1/workspaces/sample-initialization",
            headers={**token(CUSTOMER_B), "X-Workspace-ID": str(wid)},
        ).status_code
        == 403
    )
    drain(factory, wid)
    data = client.get("/api/v1/workspaces/sample-initialization", headers=headers).json()[
        "initialization"
    ]
    assert data["status"] == "COMPLETE" and data["completed"] == 21
    with factory() as s:
        runs = [s.get(ProcessingRun, UUID(rid)) for rid in s.get(SampleInstallation, wid).run_ids]
        outcomes = [
            s.scalar(select(Decision.outcome).where(Decision.run_id == run.id)) for run in runs
        ]
        assert Counter(outcomes) == {"VALIDATED": 14, "NEEDS_REVIEW": 1, "BLOCKED": 6}
        assert outcomes[1:4] == ["VALIDATED", "VALIDATED", "BLOCKED"]
        assert all(
            s.scalar(
                select(RunEvent.id).where(RunEvent.run_id == run.id, RunEvent.stage == "decision")
            )
            for run in runs
        )
        assert any(page["method"] == "OCR" for page in runs[5].pages)
        assert (
            s.scalar(
                select(func.count())
                .select_from(GmailConnection)
                .where(GmailConnection.workspace_id == wid)
            )
            == 0
        )
        po = s.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.workspace_id == wid, PurchaseOrder.number == "AF-PO-2026-003"
            )
        )
        assert s.scalar(
            select(func.sum(FinancialCommitment.amount)).where(FinancialCommitment.po_id == po.id)
        ) == Decimal("2212.50")
        before = counts(s, wid)
        assert before[:2] == (21, 21)
        document_id = runs[0].document_id
    for _ in range(3):
        assert (
            client.post("/api/v1/workspaces/sample", headers=token(CUSTOMER_A)).status_code == 201
        )
        run_once(factory)
    with factory() as s:
        assert counts(s, wid) == before
        assert (
            s.scalar(
                select(func.count())
                .select_from(InvoiceDocument)
                .where(InvoiceDocument.workspace_id != wid)
            )
            == 0
        )
    assert (
        client.get(f"/api/v1/documents/{document_id}/content", headers=headers).status_code == 200
    )


def test_worker_failure_resumes_without_extra_reservations(secure_client, monkeypatch):
    client, factory, token = secure_client
    wid, headers = create(client, token)
    import app.worker.main as worker

    original = worker.pdf_process

    def fail(*args):
        raise RuntimeError("technical fixture failure")

    monkeypatch.setattr(worker, "pdf_process", fail)
    run_once(factory)
    advance(factory)
    with factory() as s:
        row = s.get(SampleInstallation, wid)
        failed_id = row.current_run_id
        assert row.status == "FAILED" and row.completed == 0
    monkeypatch.setattr(worker, "pdf_process", original)
    assert (
        client.post("/api/v1/workspaces/sample-initialization/resume", headers=headers).status_code
        == 200
    )
    assert (
        client.post("/api/v1/workspaces/sample-initialization/resume", headers=headers).status_code
        == 200
    )
    drain(factory, wid)
    with factory() as s:
        assert s.get(ProcessingRun, failed_id).status == "FAILED"
        assert counts(s, wid)[:2] == (21, 22)
        assert (
            s.scalar(
                select(func.count())
                .select_from(FinancialCommitment)
                .join(PurchaseOrder)
                .where(PurchaseOrder.workspace_id == wid)
            )
            == 14
        )


def test_ingestion_commit_interruption_replays_existing_receipt(secure_client, monkeypatch):
    client, factory, token = secure_client
    wid, headers = create(client, token)
    import app.sample_service as sample

    original = sample.ingest

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("interruption after receipt commit")

    monkeypatch.setattr(sample, "ingest", interrupted)
    advance(factory)
    with factory() as s:
        assert s.get(SampleInstallation, wid).status == "FAILED"
        assert counts(s, wid)[:2] == (1, 1)
    monkeypatch.setattr(sample, "ingest", original)
    assert (
        client.post("/api/v1/workspaces/sample-initialization/resume", headers=headers).status_code
        == 200
    )
    advance(factory)
    advance(factory)
    with factory() as s:
        assert counts(s, wid)[:2] == (1, 1)
        assert s.get(SampleInstallation, wid).current_run_id


def test_explicit_backfill_refuses_user_edits_and_history(secure_client):
    client, factory, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    with factory.begin() as s:
        provision_sample(s, SimpleNamespace(subject=CUSTOMER_A))
    assert client.post("/api/v1/workspaces/sample", headers=token(CUSTOMER_A)).status_code == 201
    run_once(factory)
    with factory.begin() as s:
        s.delete(s.get(SampleInstallation, sample_id(CUSTOMER_A)))
    assert client.post("/api/v1/workspaces/sample", headers=token(CUSTOMER_A)).status_code == 409
    with factory() as s:
        assert counts(s, sample_id(CUSTOMER_A))[:2] == (1, 1)
    bootstrap(client, token, CUSTOMER_B)
    with factory.begin() as s:
        workspace = provision_sample(s, SimpleNamespace(subject=CUSTOMER_B))
        s.scalar(
            select(Vendor).where(Vendor.workspace_id == workspace.id)
        ).legal_name = "Retain user edit"
    assert client.post("/api/v1/workspaces/sample", headers=token(CUSTOMER_B)).status_code == 409
    with factory() as s:
        assert s.get(SampleInstallation, sample_id(CUSTOMER_B)) is None
        assert s.scalar(select(Vendor.id).where(Vendor.legal_name == "Retain user edit"))


def test_concurrent_initializers_enqueue_only_one_ordered_run(secure_client):
    from concurrent.futures import ThreadPoolExecutor

    client, factory, token = secure_client
    wid, _ = create(client, token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: advance(factory), range(2)))
    with factory() as session:
        assert counts(session, wid)[:2] == (1, 1)
        assert session.get(SampleInstallation, wid).completed == 0


def test_backfill_refuses_mailbox_connections_and_pending_consent(secure_client):
    from datetime import datetime, timedelta, timezone

    from app.models import GmailOAuthAttempt

    client, factory, token = secure_client
    for subject in [CUSTOMER_A, CUSTOMER_B]:
        bootstrap(client, token, subject)
        with factory.begin() as session:
            workspace = provision_sample(session, SimpleNamespace(subject=subject))
            if subject == CUSTOMER_A:
                record = GmailConnection(
                    workspace_id=workspace.id,
                    subject=subject,
                    email="sample-check@example.invalid",
                    history_id="preserve-checkpoint",
                    credentials=None,
                )
            else:
                record = GmailOAuthAttempt(
                    workspace_id=workspace.id,
                    subject=subject,
                    state_hash="a" * 64,
                    browser_hash="b" * 64,
                    verifier="synthetic-test-only",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            session.add(record)
        response = client.post("/api/v1/workspaces/sample", headers=token(subject))
        assert response.status_code == 409
        with factory() as session:
            assert session.get(SampleInstallation, sample_id(subject)) is None
            assert counts(session, sample_id(subject))[:2] == (0, 0)
    with factory() as session:
        assert session.scalar(select(GmailConnection.history_id)) == "preserve-checkpoint"


def test_sample_owner_with_viewer_membership_cannot_initialize(secure_client):
    from app.models import Membership

    client, factory, token = secure_client
    wid, _ = create(client, token)
    with factory.begin() as session:
        member = session.scalar(
            select(Membership).where(
                Membership.workspace_id == wid, Membership.subject == CUSTOMER_A
            )
        )
        member.role = "VIEWER"
    assert client.post("/api/v1/workspaces/sample", headers=token(CUSTOMER_A)).status_code == 403
    assert (
        client.post(
            "/api/v1/workspaces/sample-initialization/resume",
            headers={**token(CUSTOMER_A), "X-Workspace-ID": str(wid)},
        ).status_code
        == 403
    )
