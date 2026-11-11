"""Admission is isolated, lightweight, and leaves no artifacts on failure."""

import subprocess
import sys
from io import BytesIO
from uuid import UUID

import pymupdf
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import get_settings
from app.extraction.pdf import pdf_process, read_pdf
from app.ingestion import ingest
from app.models import DocumentSubmission, FinancialCommitment, InvoiceDocument, ProcessingRun
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf


def test_parent_imports_do_not_load_native_pdf_library():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.main,app.sample_service;import sys;assert 'pymupdf' not in sys.modules",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0


def test_inspection_never_decodes_text_or_renders(tmp_path, monkeypatch):
    path = tmp_path / "small.pdf"
    path.write_bytes(invoice_pdf())

    def forbidden(*args, **kwargs):
        raise AssertionError("Admission must not extract text, images or OCR")

    monkeypatch.setattr(pymupdf.Page, "get_text", forbidden)
    monkeypatch.setattr(pymupdf.Page, "get_pixmap", forbidden)
    monkeypatch.setattr(pymupdf.Page, "get_images", forbidden)
    assert read_pdf(str(path), False) == {"page_count": 1, "pages": []}
    assert pdf_process(path, False) == {"page_count": 1, "pages": []}


@pytest.mark.parametrize(
    "kind", ["invalid", "encrypted", "pages", "geometry", "oversize", "timeout"]
)
def test_rejected_inspection_has_no_records_storage_calls_or_files(workflow_db, monkeypatch, kind):
    payload = invoice_pdf()
    if kind == "invalid":
        payload = b"%PDF-invalid"
    elif kind in {"encrypted", "pages", "geometry"}:
        with pymupdf.open() as doc:
            for _ in range(21 if kind == "pages" else 1):
                doc.new_page(width=10000 if kind == "geometry" else 600)
            payload = doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256 if kind == "encrypted" else 0,
                owner_pw="synthetic-owner",
                user_pw="synthetic-user" if kind == "encrypted" else "",
            )
    elif kind == "oversize":
        monkeypatch.setenv("MAX_UPLOAD_BYTES", "32")
        get_settings.cache_clear()
    else:

        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("sensitive path", 55)

        monkeypatch.setattr("app.extraction.pdf.subprocess.run", timeout)
    calls = []
    monkeypatch.setattr("app.ingestion.persist_document", lambda *args: calls.append("put"))
    monkeypatch.setattr("app.ingestion.remove_document", lambda *args: calls.append("delete"))
    with workflow_db() as session:
        with pytest.raises(HTTPException) as caught:
            ingest(BytesIO(payload), "private.pdf", None, session)
        assert caught.value.status_code == (413 if kind == "oversize" else 422)
        assert "sensitive" not in str(caught.value.detail)
        for model in [InvoiceDocument, ProcessingRun, DocumentSubmission, FinancialCommitment]:
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert calls == []
    assert list(get_settings().storage_dir.iterdir()) == []


def test_successful_private_storage_handoff_and_recovery(workflow_db, monkeypatch):
    # Real boto3 adapter with offline SDK responses; real parsing, DB and worker.
    import boto3
    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "synthetic-private")
    get_settings.cache_clear()
    client = boto3.session.Session().client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    monkeypatch.setattr("app.storage.client", lambda: client)
    payload = invoice_pdf()
    with Stubber(client) as stub:
        # A missing/extra provider operation fails the test, never reaches real AWS.
        stub.add_response("put_object", {})
        with workflow_db() as session:
            with pytest.raises(HTTPException):
                ingest(BytesIO(b"%PDF-bad"), "bad.pdf", None, session)
            receipt = ingest(BytesIO(payload), "valid.pdf", "recovery", session)
            run = session.get(ProcessingRun, UUID(receipt["run_id"]))
            assert run.status == "QUEUED"
            document = session.get(InvoiceDocument, UUID(receipt["document_id"]))
            storage_key = document.storage_key
        assert list(get_settings().storage_dir.iterdir()) == []
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(payload), len(payload))},
            {"Bucket": "synthetic-private", "Key": "invoiceguard/" + storage_key},
        )
        assert run_once(workflow_db)
        stub.assert_no_pending_responses()
    with workflow_db() as session:
        assert session.get(ProcessingRun, UUID(receipt["run_id"])).status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 1
    assert list(get_settings().storage_dir.iterdir()) == []
