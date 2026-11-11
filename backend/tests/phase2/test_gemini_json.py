"""Controlled provider contracts: these tests make no live Gemini calls."""

import json

import httpx
import pytest

from app.config import get_settings
from app.extraction.fallback import fallback
from app.extraction.gemini import (
    MAX_RESPONSE_BYTES,
    GeminiUnavailable,
    extract_gemini,
    json_contract,
)
from app.extraction.pipeline import ExtractionModeFailure, structure
from app.extraction.schema import FIELDS, LineItem

PAGES = [
    {
        "page": 1,
        "method": "PDF_TEXT",
        "text": "INVOICE\nInvoice number: INV-1\nPurchase order: PO-1\nGrand total: 66.00\nItem: PAPER-A4 | Quantity: 3 | Unit price: 20.00 | Net: 60.00 | Tax rate: 0.10 | Tax: 6.00 | Gross: 66.00",
    }
]


def envelope(text, **candidate):
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP", **candidate}
        ]
    }


def call(handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return extract_gemini(PAGES, "synthetic-secret", "gemini-3.5-flash-lite", client)


def test_json_mode_contract_preserves_all_fields_and_exact_evidence():
    expected = fallback(PAGES)

    def handler(request):
        body = json.loads(request.content)
        assert request.url.path.endswith("/models/gemini-3.5-flash-lite:generateContent")
        assert body["generationConfig"] == {
            "temperature": 0,
            "responseMimeType": "application/json",
        }
        assert set(json_contract()) == set(type(expected).model_fields)
        prompt = body["contents"][0]["parts"][0]["text"]
        for field in [*FIELDS, *LineItem.model_fields]:
            assert '"' + field + '"' in prompt
        return httpx.Response(200, json=envelope(expected.model_dump_json()))

    actual = call(handler)
    assert actual.model_dump() == expected.model_dump()
    assert actual.invoice_number.quote == "Invoice number: INV-1"
    assert actual.invoice_number.page == 1
    assert len(actual.items) == 1
    assert actual.items[0].quantity.value == "3"
    assert actual.items[0].quantity.quote == expected.items[0].quantity.quote
    assert (
        actual.tax_id.value is None and actual.tax_id.page is None and actual.tax_id.quote is None
    )


@pytest.mark.parametrize(
    "case",
    [
        "missing_field",
        "extra_field",
        "numeric_value",
        "string_page",
        "too_many_items",
        "bad_document_type",
    ],
)
def test_schema_violations_never_become_extractions(case):
    data = fallback(PAGES).model_dump()
    if case == "missing_field":
        del data["vendor_code"]
    elif case == "extra_field":
        data["approve_invoice"] = True
    elif case == "numeric_value":
        data["total"]["value"] = 66
    elif case == "string_page":
        data["invoice_number"]["page"] = "1"
    elif case == "too_many_items":
        data["items"] = [
            {field: {"value": None, "page": None, "quote": None} for field in LineItem.model_fields}
        ] * 201
    else:
        data["document_type"] = "PURCHASE_ORDER"
    with pytest.raises(GeminiUnavailable) as caught:
        call(lambda request: httpx.Response(200, json=envelope(json.dumps(data))))
    assert caught.value.diagnostics["category"] == "schema_validation"
    assert caught.value.diagnostics["http_status"] == 200


@pytest.mark.parametrize("text", ["not JSON", "```json\n{}\n```", '{"document_type":'])
def test_invalid_json_is_not_repaired_or_guessed(text):
    with pytest.raises(GeminiUnavailable) as caught:
        call(lambda request: httpx.Response(200, json=envelope(text)))
    assert caught.value.diagnostics["category"] == "invalid_json"


@pytest.mark.parametrize(
    "status,category",
    [
        (400, "request_rejected"),
        (401, "authentication"),
        (403, "authentication"),
        (404, "model_not_found"),
        (429, "rate_limited"),
        (500, "provider_error"),
    ],
)
def test_http_diagnostics_are_safe(status, category, caplog, monkeypatch):
    monkeypatch.setattr("app.extraction.gemini.time.sleep", lambda seconds: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive invoice body and synthetic-secret")

    with pytest.raises(GeminiUnavailable) as caught:
        call(handler)
    assert caught.value.diagnostics["http_status"] == status
    assert caught.value.diagnostics["category"] == category
    assert len(calls) == (2 if status == 429 or status >= 500 else 1)
    assert "synthetic-secret" not in str(caught.value) + caplog.text + json.dumps(
        caught.value.diagnostics
    )
    assert "sensitive invoice" not in caplog.text + str(caught.value)


def test_timeout_is_classified_without_logging_exception_or_url(caplog):
    def handler(request):
        raise httpx.ReadTimeout("sensitive invoice and synthetic-secret", request=request)

    with pytest.raises(GeminiUnavailable) as caught:
        call(handler)
    assert caught.value.diagnostics["category"] == "timeout"
    assert caught.value.diagnostics["http_status"] is None
    assert "synthetic-secret" not in str(caught.value) + caplog.text


@pytest.mark.parametrize(
    "payload,category",
    [
        ({}, "invalid_envelope"),
        ({"candidates": []}, "invalid_envelope"),
        (envelope("{}", finishReason="MAX_TOKENS"), "response_incomplete"),
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "response_blocked"),
    ],
)
def test_invalid_or_incomplete_envelopes_are_not_accepted(payload, category):
    with pytest.raises(GeminiUnavailable) as caught:
        call(lambda request: httpx.Response(200, json=payload))
    assert caught.value.diagnostics["category"] == category


def test_response_size_is_bounded():
    with pytest.raises(GeminiUnavailable) as caught:
        call(lambda request: httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)))
    assert caught.value.diagnostics["category"] == "response_too_large"


def test_failure_diagnostics_survive_auto_fallback_and_strict_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-secret")
    get_settings.cache_clear()

    def fail(*args):
        raise GeminiUnavailable(
            "sensitive provider response", category="request_rejected", http_status=400
        )

    monkeypatch.setattr("app.extraction.pipeline.extract_gemini", fail)
    auto = structure(PAGES, "test-document", "AUTO")
    assert auto["provider"] == "FALLBACK" and auto["model"] is None
    assert auto["provider_diagnostics"]["http_status"] == 400
    assert auto["fields"]["invoice_number"]["verified"]
    with pytest.raises(ExtractionModeFailure) as caught:
        structure(PAGES, "test-document", "GEMINI")
    assert caught.value.metadata["provider"] == "NONE"
    assert caught.value.metadata["provider_diagnostics"]["category"] == "request_rejected"
    assert "sensitive provider" not in json.dumps(auto) + json.dumps(caught.value.metadata)
