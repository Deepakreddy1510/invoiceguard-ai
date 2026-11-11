# Gemini structured extraction compatibility

## Finding and focused change

The previous adapter sent `InvoiceExtraction.model_json_schema()` directly as `generationConfig.responseJsonSchema`. The generated schema is 2,127 JSON characters in the tested Pydantic version and includes `$defs`, `$ref`, nullable `anyOf` evidence fields, `additionalProperties: false`, enums and nested item-count constraints. A successful basic `generateContent` call does not establish that this additional schema/parameter combination is accepted by a particular model.

The reported HTTP 400 is consistent with rejection of that structured-output request surface. **The exact rejected keyword and live model compatibility cannot be confirmed here:** Codex has no configured Gemini API key, and no live provider call was made. It would be inaccurate to claim a particular schema keyword is conclusively unsupported.

The adapter now uses the simpler JSON MIME response mode:

```json
{"generationConfig":{"temperature":0,"responseMimeType":"application/json"}}
```

It sends neither `responseJsonSchema` nor `responseSchema`. A compact prompt contract is generated from the existing invoice and line-item field names, including every evidence value/page/quote field, null semantics, string decimals, document types, up to 200 items and up to 100 issues. This removes the API schema-compatibility dependency while keeping the original local model authoritative.

Every response is parsed with `InvoiceExtraction.model_validate_json(..., strict=True)`. Missing/extra fields, invalid types, invalid JSON and over-limit collections are rejected rather than repaired or guessed. Responses over 2 MiB, invalid envelopes, blocked output and explicit non-STOP completion reasons are also rejected. Source evidence verification runs afterward, unchanged. Vendor/PO resolution, duplicates, tax rules, financial decisions and Gmail permissions/settings are unchanged. An extraction result is never financial approval.

AUTO retains conservative Standard fallback on provider/response failure. Strict GEMINI mode still fails without fallback when the provider or evidence cannot be trusted. Explicit FALLBACK makes no Gemini call. Existing invoices and audit events are not rewritten.

## Safe administrator diagnostics

Provider failures log only a fixed failure category and HTTP status. The persisted extraction metadata contains `provider_diagnostics` in AUTO fallback and strict failure, accessible through the existing authorized run-detail API (`GET /api/v1/runs/{run_id}`, under `extraction.provider_diagnostics`). It includes only provider, category, status and request-format version; it does not include keys, request URLs, raw provider bodies or invoice text. Administrator service logs and the verification command below expose the same safe diagnosis without a frontend change.

Examples: `request_rejected` / HTTP 400, `authentication` / HTTP 401 or 403, `model_not_found` / HTTP 404, `rate_limited` / HTTP 429, `provider_error` / HTTP 5xx, `timeout`, `network_error`, `invalid_json`, `schema_validation`, `response_incomplete` or `response_blocked`. HTTP 429/5xx retain the existing single retry; HTTP 400 is not repeatedly retried. `not_configured` and `evidence_verification` distinguish local strict-mode failures. Sensitive exception text is not copied into fallback metadata or logs.

## Exact local live verification

Use the existing securely configured `GEMINI_API_KEY` in your local environment or repository `.env`. Do not paste a key into chat or put it in command arguments. Run this only with an invoice you are authorized to send to Gemini; the bundled fixture below is synthetic. The command reads a PDF through the existing reader/OCR and strict extraction/evidence pipeline. It makes an actual Gemini request when configured, prints only provider/model, safe diagnostics and evidence/issue counts, and **does not connect to a database or create a financial decision**.

From the repository root, Windows CMD:

```cmd
cd backend
set "GEMINI_MODEL=gemini-3.5-flash-lite"
uv run python -m scripts.verify_gemini_extraction ..\samples\invoices\valid.pdf --mode GEMINI
```

Linux/macOS, from the repository root:

```sh
cd backend
GEMINI_MODEL=gemini-3.5-flash-lite uv run python -m scripts.verify_gemini_extraction ../samples/invoices/valid.pdf --mode GEMINI
```

Success exits 0 with `provider: GEMINI`, the configured `actual_model`, and `financial_decision: not_run`. Exit 2 means no verified Gemini extraction was obtained; inspect the safe category/status. Without a key the command reports `not_configured` without making a provider request. To inspect conservative behavior explicitly, repeat with `--mode AUTO`; fallback is reported as FALLBACK with no successful model and still exits 2, so it cannot be mistaken for live Gemini success.

A successful local run against `gemini-3.5-flash-lite` remains necessary before calling the live integration verified. No deployment, database migration, Gmail permission change or Gmail-to-Gemini opt-in is part of this fix.

## Focused verification

Controlled HTTP transport tests cover the model-specific request path and JSON mode, every invoice field, source quotes/pages and nulls, line items, missing/extra fields, wrong types, invalid JSON, item limits, malformed/truncated/blocked responses, response size, timeouts and HTTP 400/401/403/404/429/500. They check retry counts and that secrets/provider content never appear in logs or diagnostics. Pipeline and worker regressions verify fallback, strict failure, evidence rejection, retained history and financial commitments.

**46 focused tests passed** (29 unrelated cases deselected). Backend Ruff lint and formatting passed. The local smoke command was also checked with no key: it exited 2 with only `not_configured` safe diagnostics. These are provider-mocked tests, not live Gemini integration tests. No full browser or backend regression suite was run for this focused fix.
