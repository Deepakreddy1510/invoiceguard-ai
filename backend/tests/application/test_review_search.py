from uuid import uuid4

from sqlalchemy import func, select

from app.main import app
from app.models import FinancialCommitment, RunEvent, Workspace
from tests.application.test_review import client_for, upload


def test_review_search_is_literal_scoped_read_only_and_before_pagination(workflow_db):
    try:
        with client_for(workflow_db) as client:
            upload(
                client,
                workflow_db,
                number="REVIEW_A",
                sku="SOURCE-CHECK-REQUIRED",
                quantity="1",
                subtotal="20",
                tax="2",
                total="22",
            )
            upload(
                client,
                workflow_db,
                number="REVIEW_B",
                sku="SOURCE-CHECK-REQUIRED",
                quantity="2",
                subtotal="40",
                tax="4",
                total="44",
            )
            with workflow_db() as session:
                before = (
                    session.scalar(select(func.count()).select_from(FinancialCommitment)),
                    session.scalar(select(func.count()).select_from(RunEvent)),
                )
            assert len(client.get("/api/v1/reviews?search=review_a").json()["tasks"]) == 1
            assert (
                len(client.get("/api/v1/reviews?search=Northstar&limit=1&offset=1").json()["tasks"])
                == 1
            )
            assert len(client.get("/api/v1/reviews?search=PO-2026-001").json()["tasks"]) == 2
            assert client.get("/api/v1/reviews?search=%25").json()["tasks"] == []
            assert len(client.get("/api/v1/reviews?search=_A").json()["tasks"]) == 1
            with workflow_db() as session:
                after = (
                    session.scalar(select(func.count()).select_from(FinancialCommitment)),
                    session.scalar(select(func.count()).select_from(RunEvent)),
                )
            assert after == before
            other = uuid4()
            with workflow_db.begin() as session:
                session.add(
                    Workspace(
                        id=other,
                        name="Other search workspace",
                        kind="CUSTOM",
                        owner_subject="local-demo-reviewer",
                    )
                )
            assert (
                client.get(
                    "/api/v1/reviews?search=REVIEW", headers={"X-Workspace-ID": str(other)}
                ).json()["tasks"]
                == []
            )
    finally:
        app.dependency_overrides.clear()
