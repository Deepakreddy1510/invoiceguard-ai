from io import BytesIO

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import get_settings
from app.ingestion import ingest
from app.models import DocumentSubmission, InvoiceDocument, ProcessingRun
from app.seed import seed
from scripts.generate_samples import invoice_pdf


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_ingestion_identity_replay_and_key_conflict(session, storage):
    seed(session)
    data = invoice_pdf()
    first = ingest(BytesIO(data), "../../anything.pdf", "first", session)
    second = ingest(BytesIO(data), "renamed.pdf", "second", session)
    assert second["replayed"] and first["run_id"] == second["run_id"]
    assert session.scalar(select(func.count()).select_from(InvoiceDocument)) == 1
    assert session.scalar(select(func.count()).select_from(ProcessingRun)) == 1
    assert session.scalar(select(func.count()).select_from(DocumentSubmission)) == 2
    with pytest.raises(HTTPException) as exc:
        ingest(BytesIO(invoice_pdf(number="DIFFERENT")), "a.pdf", "first", session)
    assert exc.value.status_code == 409
    assert len(list(storage.glob("*.pdf"))) == 1


@pytest.mark.parametrize("data", [b"", b"not pdf", b"%PDF-corrupt"])
def test_invalid_upload_rejected_without_run(session, storage, data):
    seed(session)
    with pytest.raises(HTTPException):
        ingest(BytesIO(data), "a.pdf", None, session)
    assert session.scalar(select(func.count()).select_from(ProcessingRun)) == 0
    assert list(storage.iterdir()) == []


def test_size_limit(session, storage, monkeypatch):
    seed(session)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "20")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        ingest(BytesIO(invoice_pdf()), "a.pdf", None, session)
    assert exc.value.status_code == 413


def test_commit_acknowledgement_failure_does_not_delete_stored_pdf(session, storage, monkeypatch):
    seed(session)
    original = session.commit

    def ambiguous_commit():
        original()
        raise RuntimeError("Simulated lost acknowledgement after commit")

    monkeypatch.setattr(session, "commit", ambiguous_commit)
    with pytest.raises(RuntimeError):
        ingest(BytesIO(invoice_pdf()), "a.pdf", None, session)
    assert len(list(storage.glob("*.pdf"))) == 1
    assert session.scalar(select(func.count()).select_from(InvoiceDocument)) == 1
