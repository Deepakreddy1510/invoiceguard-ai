"""Prove the additive migration preserves actual pre-existing financial history."""

from io import BytesIO
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.ingestion import ingest
from app.models import Base
from app.seed import seed
from app.worker.main import run_once
from scripts.dataset_v2.isolation import DatabasePool, child_environment
from scripts.generate_samples import invoice_pdf


def test_workspace_migration_preserves_real_invoice_history(monkeypatch, tmp_path):
    import os

    admin = os.environ.get(
        "EVAL_ADMIN_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
    )
    # The pool can drop only databases created by this invocation. Never the demo.
    with DatabasePool(admin) as pool:
        _, url = pool.create()
        for key, value in child_environment(url, tmp_path, "fallback").items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(url)
        try:
            factory = sessionmaker(engine)
            with factory.begin() as session:
                seed(session)
            with factory() as session:
                receipt = ingest(
                    BytesIO(invoice_pdf()), "migration-proof.pdf", "migration-proof", session
                )
            run_once(factory, run_id=UUID(receipt["run_id"]))

            def snapshot():
                with engine.connect() as connection:
                    records = {
                        table: connection.execute(
                            text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY id')
                        )
                        .scalars()
                        .all()
                        for table in Base.metadata.tables
                        if table != "workspaces"
                    }
                    records["workspaces"] = connection.execute(
                        text("SELECT id::text, name FROM workspaces ORDER BY id")
                    ).all()
                    return records

            before = snapshot()
            # Return this owned fixture to the pre-change schema, then perform the upgrade.
            command.downgrade(config, "0006")
            command.upgrade(config, "head")
            assert snapshot() == before
            command.check(config)
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM decisions WHERE outcome='VALIDATED'")
                    ).scalar()
                    == 1
                )
                assert (
                    connection.execute(
                        text(
                            "SELECT count(*) FROM financial_commitments WHERE status='RESERVED' AND amount=550"
                        )
                    ).scalar()
                    == 1
                )
        finally:
            engine.dispose()
            get_settings.cache_clear()
