# Workspace and procurement verification

Verified in the managed Linux workspace on 2026-11-04, extending base commit `117b98febe81e886a4fb8fc091b24657eb61b051`. No deployment, paid resources, public URL, real Gemini key, original-demo database mount or financial-engine changes were involved.

## Actual results

| Check | Actual result |
|---|---|
| Full backend `pytest -q` | **138 passed, 0 failed**; includes the 107 pre-existing regressions |
| Frontend Vitest | **25 passed, 0 failed**, five test files; preserves the original 11 cases |
| Real-service Playwright | **11 passed, 0 failed**; includes the original 10 scenarios plus the new product workflow |
| Backend Ruff lint and formatting | Passed |
| Frontend Prettier, ESLint, TypeScript | Passed |
| Production Vite build | Passed |
| Additive migration 0007 | Passed in an invocation-owned, disposable database; Alembic reports no new upgrade operations/model drift |
| Historical migration preservation | Actual invoice validated and reserved 550; all historical table rows and original workspace IDs/names compared before/after 0006 → 0007 and remained equal |
| Financial-engine integrity | Original SHA-256 remains `f61250c319ad33e4457d6f4ffbcdaf35b5dbc9160a48b5728751408c05337072` |
| Secrets | Pinned Gitleaks 8.24.3 (release archive checksum verified), default detectors plus existing narrowly scoped provenance configuration: zero findings in source inventory |
| Live Gemini | **UNVERIFIED — no key configured; no successful live API call claimed** |

The one backend warning is the existing upstream Starlette/httpx TestClient deprecation. Browser output also reports Node's inherited NO_COLOR/FORCE_COLOR warning; these are not test failures.

Actual commands were run from the corresponding directory: `ruff format`, `ruff format --check`, `ruff check`, `pytest -q`; `npm run format`, `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`; and `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m scripts.browser_regression`. The migration regression executes upgrade/downgrade/upgrade and `alembic.command.check` only in its own random database. Initial failures (catalogue path, a case-sensitive browser locator, persisted item edit compatibility and a new footer-link accessibility finding) were fixed before these final results.

The existing OCR browser test previously used a long decimal timestamp as an invoice identifier. A rerun showed Tesseract inserting a space inside that generated identifier. Its identifier is now shorter, using base36; the test still requires the exact independently generated number, actual OCR execution, real events and a financial decision. No parser, evidence verifier, financial rule or expected decision was adjusted to raise a score. OCR accuracy on arbitrary documents remains a limitation.

## Real functionality exercised

- Backend-enforced local and OIDC workspace isolation, private per-subject My provisioning, forged headers and cross-workspace IDs denied. VIEWER procurement writes rejected. Concurrent identical vendor creates produce one record and one conflict.
- Empty private workspace, idempotent bootstrap and preserved pre-existing demo commitments. Fresh demo creates **18 vendors, 36 POs and 16 real queued PDFs** in a separate workspace; repeated creation request IDs do not add invoices. The test executes the worker and observes actual VALIDATED, NEEDS_REVIEW and BLOCKED decisions.
- Vendor creation, normalized duplicate rejection, metadata version conflicts, deactivation, unused deletion and dependency retention. A vendor matched in a decision is retained even when the invoice number is absent and no canonical invoice exists.
- Itemized and amount-based POs; invalid dates, unsupported currencies, decimal strings, reconciliation and partial-status constraints. All six supported currencies exercised. PO edit/delete locks after financial history; cancellation preserves capacity.
- Actual new private vendor → new PO → PDF → source evidence → deterministic decision. Partial billing, business duplicates, overbilling, missing fields and scanned OCR; reserved and available capacity verified. Settled-invoice deletion leaves settlement intact.
- CSV preview, row errors, all-or-nothing import, duplicate rejection, formula rejection and idempotent replay. Browser downloads the real template and imports an actual vendor into PostgreSQL.
- FALLBACK never invokes Gemini even with a configured synthetic test key. AUTO provider failure records a sanitized fallback reason. Mocked GEMINI success/failure/unsupported-evidence contracts preserve requested/actual provider distinctions, history, canonical identity and consuming capacity. No provider response body or key is exposed.
- Browser switches Demo/My, creates and edits an unused PO using stored decimal strings, uploads a matching invoice reserving **USD 66.00** of **USD 220.00** (available **USD 154.00**), blocks a subsequent **USD 176.00** request, checks audit/dashboard/history and reload persistence, and verifies Demo records remain separate. Existing live polling, manual run selection, review corrections, original PDFs and OCR scenarios continue to run.
- Automated WCAG A/AA checks cover Overview, Vendors, Purchase Orders, Exception Review, Audit and Processing; existing desktop/mobile navigation checks pass. Automated scanning is not a claim of exhaustive accessibility certification.

## Files added or changed

Backend foundations and API integration:

- `backend/app/models.py`, `backend/app/config.py`, `backend/app/auth.py`, `backend/app/main.py`, `backend/app/operations_api.py`, `backend/app/workflow_api.py`.
- New `backend/app/workspace_service.py`, `backend/app/workspaces_api.py`.
- New `backend/app/procurement.py`, `backend/app/procurement_api.py`, `backend/app/procurement_imports.py`.
- `backend/app/ingestion.py`, `backend/app/extraction/pipeline.py`, `backend/app/worker/main.py`, `backend/app/review/service.py` for mode selection and auditable re-extraction through the existing engine.
- New additive migration `backend/migrations/versions/0007_workspaces_procurement_modes.py`.
- New regressions `backend/tests/application/test_product.py`, `backend/tests/application/test_workspace_migration.py`.

Frontend:

- `frontend/src/App.tsx`, `frontend/src/client.ts`, `frontend/src/api.ts`, `frontend/src/models.ts`, `frontend/src/styles.css`.
- New `frontend/src/workspaces.tsx`, `frontend/src/pages/Vendors.tsx`, `frontend/src/POEditor.tsx`, `frontend/src/ProcurementImport.tsx`.
- `frontend/src/InvoiceWorkflow.tsx`, `frontend/src/RunDetails.tsx`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/PurchaseOrders.tsx`.
- `frontend/src/App.test.tsx`, `frontend/src/InvoiceWorkflow.test.tsx`, new `frontend/src/client.test.tsx`, new `frontend/src/POEditor.test.tsx`.
- New `frontend/e2e/product.spec.ts`; `frontend/e2e/redesign.spec.ts` adds Vendors accessibility coverage and a shorter generated OCR test identifier.

Documentation/configuration: `.env.example`, `README.md`, new `docs/workspaces-procurement.md`, and this verification record. No dependencies, financial rules, frozen dataset fixtures, hosted credentials or deployment configuration were changed.

## Limits and operational notes

The Docker project `invoiceguard-verification` uses a new PostgreSQL volume. Original `invoiceguard-ai_postgres_data` was never mounted. Browser/migration databases are disposable and ownership-checked; regular backend tests use the dedicated `invoiceguard_test` database. Local run logs, screenshots generated by the pre-existing browser tests, uploaded documents, private configuration and build outputs remain ignored and unpublished.

This environment exposes no forwarded interactive preview. GitHub publication is not hosting; this task does not deploy a public website. Use the [exact Windows CMD upgrade/start commands](workspaces-procurement.md) to open the actual application on your own computer. Hosted Auth0/S3 verification and live Gemini require separate securely configured providers and were not tested here.

Identity and financial-history restrictions are deliberate: no arbitrary PO amendments after history, no ordinary deletion of audited uploads, no fabricated opening billed balance, and no automatic release of settled capacity. Existing review/rejection workflows remain available. A fresh demo queues real work and needs a running worker before examples complete. Local mode remains a single trusted development identity, not hosted multi-user authentication. These synthetic tests are regression evidence, not a claim of extraction generalization across real suppliers.
