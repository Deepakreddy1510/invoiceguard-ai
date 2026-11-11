import json
import subprocess

import httpx
import pytest

from app.extraction.evidence import verify
from app.extraction.fallback import fallback
from app.extraction.gemini import GeminiUnavailable, extract_gemini
from app.extraction.pdf import PDFError, pdf_process, read_pdf
from app.extraction.pipeline import structure
from scripts.generate_samples import invoice_pdf


@pytest.mark.parametrize("settings", [{}, {"alternate": True}, {"scanned": True}])
def test_real_pdf_extraction(settings, tmp_path):
    path = tmp_path / "arbitrary-name.pdf"
    path.write_bytes(invoice_pdf(**settings))
    pages = pdf_process(path, True)["pages"]
    result = verify(fallback(pages), pages, "document-test")
    assert result["invoice_number"]["value"] == "SYN-INV-001"
    assert result["total"]["value"] == "550.00"
    assert result["total"]["verified"]
    assert result["items"][0]["quantity"]["value"] == "25"
    assert pages[0]["method"] == ("OCR" if settings.get("scanned") else "PDF_TEXT")


def test_corrupt_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-broken")
    with pytest.raises(PDFError):
        pdf_process(path, True)


def test_ocr_failure_explicit(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    path.write_bytes(invoice_pdf(scanned=True))

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 20)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.TimeoutExpired):
        read_pdf(str(path))


def test_evidence_rejects_hallucinated_value(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]
    result = fallback(pages)
    result.total.value = "9999"
    assert not verify(result, pages, "doc")["total"]["verified"]


def test_ambiguous_and_missing_values(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf(missing=True))
    pages = read_pdf(str(path))["pages"]
    pages[0]["text"] += "\nCurrency: EUR\n"
    result = fallback(pages)
    assert result.invoice_number.value is None
    assert result.currency.value is None


@pytest.mark.parametrize("mode", ["timeout", "malformed", "rate_limit", "auth"])
def test_gemini_failure_is_conservative(mode, tmp_path, monkeypatch):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]

    def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("timeout")
        if mode == "rate_limit":
            return httpx.Response(429)
        if mode == "auth":
            return httpx.Response(403)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"total":12}'}]}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GeminiUnavailable):
            extract_gemini(pages, "not-real", "test-model", client)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-only")
    from app.config import get_settings

    get_settings.cache_clear()

    def unavailable(*args):
        raise GeminiUnavailable("Gemini timed out.")

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", unavailable)
    try:
        result = structure(pages, "doc")
        assert result["provider"] == "FALLBACK"
        assert result["fields"]["total"]["verified"]
        assert "timed out" in result["fallback_reason"]
    finally:
        get_settings.cache_clear()


def test_gemini_real_request_contract(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]
    expected = fallback(pages)

    def handler(request):
        body = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "synthetic-key"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseJsonSchema" not in body["generationConfig"]
        assert "responseSchema" not in body["generationConfig"]
        assert "Invoice number:" in body["contents"][0]["parts"][0]["text"]
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": expected.model_dump_json()}]}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = extract_gemini(pages, "synthetic-key", "test-model", client)
    assert result.invoice_number.value == "SYN-INV-001"


def test_gemini_cannot_select_one_of_ambiguous_source_values(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]
    result = fallback(pages)
    pages[0]["text"] += "\nGrand total: 990.00\n"
    assert not verify(result, pages, "doc")["total"]["verified"]


def test_wrong_field_quote_does_not_verify_total(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]
    result = fallback(pages)
    result.total.value = "500.00"
    result.total.quote = "Subtotal: 500.00"
    assert not verify(result, pages, "doc")["total"]["verified"]


def test_page_count_and_encrypted_pdf_rejected(tmp_path):
    import pymupdf

    path = tmp_path / "pages.pdf"
    doc = pymupdf.open()
    for _ in range(21):
        doc.new_page()
    doc.save(path)
    doc.close()
    with pytest.raises(PDFError):
        pdf_process(path, False)
    path = tmp_path / "encrypted.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="synthetic-owner",
        user_pw="synthetic-user",
    )
    doc.close()
    with pytest.raises(PDFError):
        pdf_process(path, False)


def test_model_item_fields_cannot_be_mixed_across_rows(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(invoice_pdf())
    pages = read_pdf(str(path))["pages"]
    result = fallback(pages)
    pages[0]["text"] += (
        "\nItem: OTHER | Quantity: 2 | Unit price: 20.00 | Net: 40 | Tax rate: 0.10 | Tax: 4 | Gross: 44\n"
    )
    result.items[0].quantity.value = "2"
    result.items[0].quantity.quote = "Quantity: 2"
    assert not verify(result, pages, "doc")["items"][0]["quantity"]["verified"]
