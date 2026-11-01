"""Executed evaluation; no expected fields are supplied to extraction."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import DEMO_WORKSPACE_ID
from app.extraction.evidence import equivalent, verify
from app.extraction.fallback import fallback
from app.extraction.pdf import pdf_process
from app.models import InvoiceDocument, ProcessingRun
from app.seed import seed
from app.validation.engine import evaluate


def evaluate_corpus(database_url):
    # Evaluation may insert identities, so every case runs in its own rolled-back transaction.
    from sqlalchemy.engine import make_url

    if not (make_url(database_url).database or "").endswith("_test"):
        raise ValueError("Evaluation requires an isolated *_test database.")
    root = Path("../samples/extraction")
    manifest = json.loads((root / "manifest.json").read_text())
    engine = create_engine(database_url)
    results = []
    correct = eligible = missing = unsupported = review = failures = 0
    for case in manifest["cases"]:
        try:
            pages = pdf_process(root / case["file"], True)["pages"]
            doc_id = uuid4()
            fields = verify(fallback(pages), pages, str(doc_id))
            comparisons = {}
            for field, expected in case["expected"].items():
                actual = fields[field]["value"]
                if expected is None:
                    missing += int(actual is None)
                    unsupported += int(actual is not None)
                    continue
                eligible += 1
                ok = actual is not None and equivalent(field, actual, expected)
                correct += int(ok)
                unsupported += int(actual is not None and not fields[field]["verified"])
                comparisons[field] = ok
            with engine.connect() as connection:
                transaction = connection.begin()
                with Session(bind=connection) as session:
                    seed(session)
                    doc = InvoiceDocument(
                        id=doc_id,
                        workspace_id=DEMO_WORKSPACE_ID,
                        sha256=str(uuid4()),
                        storage_key=str(uuid4()),
                        byte_size=(root / case["file"]).stat().st_size,
                        page_count=len(pages),
                    )
                    session.add(doc)
                    session.flush()
                    run = ProcessingRun(document_id=doc_id)
                    session.add(run)
                    session.flush()
                    outcome, *_ = evaluate(session, run, {"fields": fields})
                    review += int(outcome == "NEEDS_REVIEW")
                transaction.rollback()
            results.append(
                {
                    "file": case["file"],
                    "provider": "FALLBACK",
                    "ocr_pages": [p["page"] for p in pages if p["method"] == "OCR"],
                    "correct_fields": comparisons,
                    "outcome": outcome,
                    "expected_outcome": case["expected_outcome"],
                }
            )
        except Exception as exc:
            failures += 1
            results.append({"file": case["file"], "technical_failure": type(exc).__name__})
    engine.dispose()
    return {
        "provider": "FALLBACK",
        "live_gemini_evaluated": False,
        "eligible_present_fields": eligible,
        "correct_present_fields": correct,
        "correct_missing_abstentions": missing,
        "unsupported_values": unsupported,
        "review_count": review,
        "invoice_count": len(manifest["cases"]),
        "technical_failures": failures,
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default="postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/invoiceguard_test",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_corpus(args.database_url), indent=2))
