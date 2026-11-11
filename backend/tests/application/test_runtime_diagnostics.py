"""Safe crash/storage metrics and a compact queue query, with no live provider calls."""

import logging
from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import event

from app.ingestion import ingest
from app.runtime_diagnostics import memory_snapshot
from app.storage import log_storage_failure
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf
from tests.application.test_review import client_for


def test_memory_metrics_allowlist_and_no_raw_values(tmp_path):
    (tmp_path / "memory.current").write_text("12345")
    (tmp_path / "memory.max").write_text("536870912")
    (tmp_path / "memory.events").write_text("oom 1\noom_kill 1\nsecret invoice-content\nmax 3")
    result = memory_snapshot(cgroup=tmp_path, proc=tmp_path / "proc")
    assert result == {
        "memory_bytes": 12345,
        "memory_limit_bytes": 536870912,
        "memory_event_oom": 1,
        "memory_event_oom_kill": 1,
        "memory_event_max": 3,
    }
    assert "secret" not in str(result)
    assert memory_snapshot(cgroup=tmp_path / "absent", proc=tmp_path / "absent") == {}


@pytest.mark.parametrize(
    "code,expected", [("AccessDenied", "AccessDenied"), ("secret-bucket-name", "provider_error")]
)
def test_storage_log_never_exposes_provider_message_or_object_names(caplog, code, expected):
    exc = ClientError(
        {
            "Error": {"Code": code, "Message": "private invoice or credential"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "PutObject",
    )
    with caplog.at_level(logging.ERROR):
        log_storage_failure("upload", exc)
    assert f"category={expected}" in caplog.text and "http_status=403" in caplog.text
    assert "private invoice" not in caplog.text and "secret-bucket-name" not in caplog.text


def test_queue_poll_does_not_load_ocr_pages_and_detail_still_returns_them(workflow_db):
    with workflow_db() as session:
        receipt = ingest(BytesIO(invoice_pdf()), "source.pdf", None, session)
        engine = session.bind
    assert run_once(workflow_db)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    with client_for(workflow_db) as client:
        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get("/api/v1/runs")
            assert response.status_code == 200
            summary = response.json()["runs"][0]
            assert summary["id"] == receipt["run_id"] and summary["outcome"] == "VALIDATED"
            assert "processing_runs.pages" not in " ".join(statements)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        detail = client.get("/api/v1/runs/" + receipt["run_id"]).json()
        assert detail["pages"] and detail["events"]
