"""Real source PDFs exercise uncertainty and policy edges without invented facts."""

from io import BytesIO
from uuid import UUID

import pymupdf
import pytest
from sqlalchemy import func, select

from app.config import DEMO_WORKSPACE_ID
from app.ingestion import ingest
from app.models import Decision, FinancialCommitment, ProcessingRun, PurchaseOrder
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf


@pytest.mark.parametrize(
    "case,expected",
    [
        ("missing_total", "NEEDS_REVIEW"),
        ("ambiguous_po", "NEEDS_REVIEW"),
        ("cancelled_po", "BLOCKED"),
        ("currency_mismatch", "BLOCKED"),
    ],
)
def test_uncertain_or_unauthorized_pdf_never_consumes_capacity(workflow_db, case, expected):
    factory = workflow_db
    payload = invoice_pdf(
        number="PS1-" + case, currency="EUR" if case == "currency_mismatch" else "USD"
    )
    if case in ["missing_total", "ambiguous_po"]:
        with pymupdf.open(stream=payload, filetype="pdf") as document:
            page = document[0]
            if case == "missing_total":
                rectangles = page.search_for("Grand total: 550.00")
                assert rectangles
                for rectangle in rectangles:
                    page.add_redact_annot(rectangle)
                page.apply_redactions()
            else:
                page.insert_text(
                    (40, page.rect.height - 25), "Purchase order: PO-2026-001 or PO-2026-002"
                )
            payload = document.tobytes()
    if case == "cancelled_po":
        with factory.begin() as s:
            s.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.workspace_id == DEMO_WORKSPACE_ID,
                    PurchaseOrder.number == "PO-2026-001",
                )
            ).status = "CANCELLED"
    with factory() as s:
        receipt = ingest(BytesIO(payload), "source.pdf", None, s, extraction_mode="FALLBACK")
    assert run_once(factory, run_id=UUID(receipt["run_id"]))
    with factory() as s:
        run = s.get(ProcessingRun, UUID(receipt["run_id"]))
        assert run.status == "SUCCEEDED"
        assert run.extraction["provider"] == "FALLBACK" and run.extraction["model"] is None
        if case == "missing_total":
            assert run.extraction["fields"]["total"]["value"] is None
        if case == "ambiguous_po":
            assert run.extraction["fields"]["po_number"]["value"] is None
        assert s.scalar(select(Decision.outcome).where(Decision.run_id == run.id)) == expected
        assert s.scalar(select(func.count()).select_from(FinancialCommitment)) == 0


def test_gemini_cannot_verify_one_po_when_source_also_contains_ambiguous_reference():
    from app.extraction.evidence import verify
    from app.extraction.fallback import fallback

    pages = [
        {
            "page": 1,
            "method": "PDF_TEXT",
            "text": "INVOICE\nPurchase order: PO-2026-001\nPurchase order: PO-2026-001 or PO-2026-002",
        }
    ]
    extracted = fallback(pages)
    assert extracted.po_number.value is None
    # A model selecting the convenient source line still cannot verify it.
    extracted.po_number.value = "PO-2026-001"
    extracted.po_number.page = 1
    extracted.po_number.quote = "Purchase order: PO-2026-001"
    checked = verify(extracted, pages, "synthetic-document")
    assert checked["po_number"]["verified"] is False


def test_failed_auto_gemini_records_attempt_without_claiming_model_success(monkeypatch):
    from app.config import get_settings
    from app.extraction.gemini import GeminiUnavailable
    from app.extraction.pipeline import structure

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-provider-contract-only")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-contract-test")
    get_settings.cache_clear()

    def fail(*args):
        raise GeminiUnavailable("Controlled provider failure")

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", fail)
    pages = [{"page": 1, "method": "PDF_TEXT", "text": "INVOICE\nPurchase order: PO-2026-001"}]
    result = structure(pages, "synthetic-document", "AUTO")
    assert result["provider"] == "FALLBACK" and result["model"] is None
    assert result["attempted_provider"] == "GEMINI"
    assert result["attempted_model"] == "gemini-contract-test"
    assert result["fallback_reason"]
    standard = structure(pages, "synthetic-document", "FALLBACK")
    assert standard["attempted_provider"] is None and standard["attempted_model"] is None
