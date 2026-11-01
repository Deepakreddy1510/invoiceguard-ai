from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from threading import Barrier

import pytest
from sqlalchemy import func, select
from test_financial import prepare

from app.ingestion import ingest
from app.models import Decision, FinancialCommitment, ProcessingRun, RunEvent
from app.worker.main import claim, finalize, process
from scripts.generate_samples import invoice_pdf


@pytest.mark.parametrize("same_identity", [False, True])
def test_simultaneous_finalizations_no_overconsumption(workflow_db, tmp_path, same_identity):
    factory = workflow_db
    with factory.begin() as session:
        a = prepare(
            session,
            tmp_path,
            number="RACE-A",
            quantity="60",
            subtotal="1200",
            tax="120",
            total="1320",
        )
        b = prepare(
            session,
            tmp_path,
            number="RACE-A" if same_identity else "RACE-B",
            quantity="60" if same_identity else "55",
            subtotal="1200" if same_identity else "1100",
            tax="120" if same_identity else "110",
            total="1320" if same_identity else "1210",
        )
        jobs = [(a.id, a.lease_token), (b.id, b.lease_token)]
    barrier = Barrier(2)

    def finish(job):
        with factory.begin() as session:
            barrier.wait(timeout=10)
            return finalize(session, *job).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(finish, jobs))
    assert sorted(outcomes) == ["BLOCKED", "VALIDATED"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 1
        assert session.scalar(select(func.sum(FinancialCommitment.amount))) <= Decimal("2200")


def test_interrupted_worker_reclaimed_and_fenced(workflow_db):
    factory = workflow_db
    with factory() as session:
        record = ingest(BytesIO(invoice_pdf()), "unknown.pdf", None, session)
    first = claim(factory)
    assert first is not None
    with factory.begin() as session:
        run = session.get(ProcessingRun, first[0])
        run.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    second = claim(factory)
    assert first[1] != second[1]
    process(first, factory)  # stale worker cannot add stages or decisions
    process(second, factory)
    with factory() as session:
        run = session.get(ProcessingRun, second[0])
        assert run.status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 1
        assert session.scalar(select(func.count()).select_from(Decision)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(RunEvent).where(RunEvent.outcome == "RETRY_WAIT")
            )
            == 1
        )
        # New independent session reconstructs result and events, not browser memory.
        assert record["run_id"] == str(run.id)


def test_finalize_rollback_is_atomic(workflow_db, tmp_path):
    factory = workflow_db
    with factory.begin() as session:
        run = prepare(session, tmp_path)
        run_id, token = run.id, run.lease_token
    with pytest.raises(RuntimeError), factory.begin() as session:
        finalize(session, run_id, token)
        raise RuntimeError("simulated transaction failure before commit")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Decision)) == 0
        assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 0
    with factory.begin() as session:
        assert finalize(session, run_id, token).outcome == "VALIDATED"
