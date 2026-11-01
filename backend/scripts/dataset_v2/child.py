"""Input-only process. Does not load any oracle or expected decisions."""

import argparse
import json
from pathlib import Path

from sqlalchemy.engine import make_url

from scripts.dataset_v2.isolation import validate_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["extraction", "worker", "migrate"], required=True)
    parser.add_argument("--pdf")
    parser.add_argument("--output")
    args = parser.parse_args()
    from app.config import get_settings

    settings = get_settings()
    validate_name(make_url(settings.database_url).database)
    if args.mode == "migrate":
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
        return
    if args.mode == "extraction":
        import hashlib

        from app.extraction.pdf import pdf_process
        from app.extraction.pipeline import structure

        pages = pdf_process(Path(args.pdf), True)["pages"]
        result = {
            "extraction": structure(pages, hashlib.sha256(Path(args.pdf).read_bytes()).hexdigest()),
            "pages": pages,
        }
    else:
        from app.db import SessionLocal
        from app.ingestion import ingest
        from app.models import ProcessingRun
        from app.worker.main import run_once

        with Path(args.pdf).open("rb") as stream, SessionLocal() as session:
            receipt = ingest(stream, Path(args.pdf).name, None, session)
        if not receipt["replayed"]:
            run_once(SessionLocal)
        from uuid import UUID

        with SessionLocal() as session:
            run = session.get(ProcessingRun, UUID(receipt["run_id"]))
            result = {**receipt, "status": run.status, "error": run.error}
    Path(args.output).write_text(json.dumps(result))


if __name__ == "__main__":
    main()
