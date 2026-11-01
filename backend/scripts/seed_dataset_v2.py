"""Validate catalogue seeding in a new disposable DB; never upsert a demo."""

import argparse
import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import FinancialCommitment, PurchaseOrder, Vendor
from scripts.dataset_v2.common import DATA, load, write_json
from scripts.dataset_v2.isolation import DatabasePool
from scripts.dataset_v2.runner import invoke, observation, snapshot
from scripts.dataset_v2.seed import seed_catalogue

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    admin = os.environ.get(
        "EVAL_ADMIN_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
    )
    cat = load(DATA / "procurement.json")
    manifest = load(DATA / "manifest.json")
    with DatabasePool(admin) as pool, tempfile.TemporaryDirectory() as temp:
        name, url = pool.create()
        invoke("migrate", url, Path(temp), "fallback")
        engine = create_engine(url)
        try:
            seed_catalogue(engine, cat)
            for entry in manifest["baseline"]:
                receipt = invoke("worker", url, Path(temp), "fallback", DATA / entry["file"])
                assert observation(engine, receipt, cat)["actual_decision"] == "VALIDATED"
            with Session(engine) as session:
                report = {
                    "vendors": session.scalar(select(func.count()).select_from(Vendor)),
                    "purchase_orders": session.scalar(
                        select(func.count()).select_from(PurchaseOrder)
                    ),
                    "baseline_commitments": session.scalar(
                        select(func.count()).select_from(FinancialCommitment)
                    ),
                    "balances": snapshot(engine, cat)["balances"],
                    "database": name,
                    "disposable": True,
                }
        finally:
            engine.dispose()
    report["database_removed"] = True
    write_json(args.report, report)
    print({k: v for k, v in report.items() if k != "balances"})
