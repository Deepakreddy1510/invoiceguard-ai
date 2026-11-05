"""Upgrade canonical and earlier prototype schemas without rewriting financial rows."""

from io import BytesIO
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import DEMO_WORKSPACE_ID, get_settings
from app.ingestion import ingest
from app.models import Base, EmailIntakeEvent, GmailConnection
from app.seed import seed
from app.worker.main import run_once
from scripts.dataset_v2.isolation import DatabasePool, child_environment
from scripts.generate_samples import invoice_pdf


def test_workspace_upgrade_repairs_optional_legacy_evidence_and_keeps_ledger(monkeypatch, tmp_path):
    import os

    admin = os.environ.get(
        "EVAL_ADMIN_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
    )
    with DatabasePool(admin) as pool:
        _, url = pool.create()
        for key, value in child_environment(url, tmp_path, "fallback").items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(url)
        factory = sessionmaker(engine)
        try:
            with factory.begin() as session:
                seed(session)
                connection = GmailConnection(
                    workspace_id=DEMO_WORKSPACE_ID,
                    subject="local-demo-reviewer",
                    email="migration@example.invalid",
                    history_id="100",
                    credentials=None,
                )
                session.add(connection)
                session.flush()
                session.add(
                    EmailIntakeEvent(
                        workspace_id=DEMO_WORKSPACE_ID,
                        connection_id=connection.id,
                        stage="connection",
                        outcome="SUCCEEDED",
                        detail="Retained migration source record",
                    )
                )
            with factory() as session:
                receipt = ingest(
                    BytesIO(invoice_pdf(number="LIFECYCLE-MIGRATION")),
                    "retained.pdf",
                    None,
                    session,
                    extraction_mode="FALLBACK",
                )
            assert run_once(factory, run_id=UUID(receipt["run_id"]))

            def snapshot():
                with engine.connect() as conn:
                    result = {
                        table: conn.execute(
                            text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY id')
                        )
                        .scalars()
                        .all()
                        for table in Base.metadata.tables
                        if table not in ["workspaces", "email_intake_events"]
                    }
                    result["email"] = conn.execute(
                        text(
                            "SELECT id,workspace_id,connection_id,stage,outcome,detail,created_at FROM email_intake_events ORDER BY id"
                        )
                    ).all()
                    result["workspaces"] = conn.execute(
                        text(
                            "SELECT id,name,kind,owner_subject,created_at FROM workspaces ORDER BY id"
                        )
                    ).all()
                    return result

            before = snapshot()
            command.downgrade(config, "0008")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE email_intake_events DROP COLUMN evidence"))
            command.upgrade(config, "head")
            assert snapshot() == before
            command.check(config)
            with engine.connect() as conn:
                assert (
                    conn.execute(text("SELECT evidence FROM email_intake_events")).scalar() is None
                )
                assert conn.execute(text("SELECT version,archived_at FROM workspaces")).one() == (
                    1,
                    None,
                )
        finally:
            engine.dispose()
