"""Explicit reproduction, outside ordinary regression; exits 2 on a mismatch."""

import argparse
import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from scripts.dataset_v2.common import DATA, PRIVATE, load, write_json
from scripts.dataset_v2.isolation import DatabasePool
from scripts.dataset_v2.runner import gold_submit, invoke, observation
from scripts.dataset_v2.seed import seed_catalogue

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    manifest = load(DATA / "manifest.json")
    cat = load(DATA / "procurement.json")
    entry = next(
        d for d in manifest["documents"] if d["id"] == args.case and d["split"] == args.split
    )
    path = (
        DATA / "development/answers.json"
        if args.split == "development"
        else PRIVATE / "oracle.json"
    )
    answer = load(path)["cases"][args.case]
    if entry["order"] != 0:
        raise ValueError("This focused reproduction accepts independent first-step cases only.")
    admin = os.environ.get(
        "EVAL_ADMIN_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
    )
    with DatabasePool(admin) as pool, tempfile.TemporaryDirectory() as temp:
        _, url = pool.create()
        invoke("migrate", url, Path(temp), "fallback")
        engine = create_engine(url)
        try:
            seed_catalogue(engine, cat)
            for b in manifest["baseline"]:
                invoke("worker", url, Path(temp), "fallback", DATA / b["file"])
            receipt = gold_submit(engine, entry, answer)
            result = observation(engine, receipt, cat)
        finally:
            engine.dispose()
    report = {
        "case": args.case,
        "expected": answer["expected_decision"],
        "actual": result["actual_decision"],
        "matching_rules": [r for r in result["rules"] if r["rule_id"].startswith("VENDOR")],
        "database_removed": True,
    }
    write_json(args.report, report)
    print(report)
    raise SystemExit(0 if report["expected"] == report["actual"] else 2)
