> Historical local verification snapshot, before the subsequently authorized GitHub publication. See [publication verification](publication-verification.md) for current repository/deployment status.

# Integrated application verification — 2026-11-01

The core application works end-to-end locally, including real PDFs, OCR, persisted decisions/reservations, reviewer corrections and browser workflows. External website delivery remains blocked on explicit deployment approval, hosting credentials and provider network access. Nothing was committed, pushed, deployed, purchased or published.

## Actual checks

| Check | Actual result |
|---|---|
| Backend pytest | **107 passed, 0 failed**, 16.03 seconds; one upstream Starlette/httpx deprecation warning |
| React component tests | **4 passed, 0 failed** |
| Browser tests | **8 passed, 0 failed**, final run 27.7 seconds, actual Chromium + API + worker + disposable PostgreSQL |
| Ruff lint / format | Passed; 81 Python files formatted |
| TypeScript and Vite production build | Passed; largest output chunk approximately 247 KB before gzip |
| Alembic current / check | `0006 (head)`; no new upgrade operations detected |
| Docker production build | Passed, nonroot runtime, compiled React and Tesseract installed |
| Final container integration | Passed: real PDF → API → S3-compatible storage → worker → PostgreSQL → VALIDATED; ten actual persisted events |
| Object persistence | Original PDF retrieved from private API after local storage-container restart |
| Hosted authentication guard | Production-mode container rejects anonymous dashboard, review, audit and document access with 401 |
| JWT authorization | Real RSA signatures/issuer/audience/expiry and membership/role/workspace isolation tested with generated test keys; external Auth0 not tested |
| Running demonstration UI | React and real API proxy return 200, 18 vendors/36 POs, five primary route groups loaded without uncaught/API errors; desktop visual inspection and mobile browser assertions passed |
| Application restart | Same 16 runs, unique invoice count and persisted events after restarting API/worker/frontend |
| Repeated demo seeding | No additional documents, runs or commitments; original workspace still 10 documents and five commitments |
| Frozen dataset integrity | 128 document hashes verified; 18 vendors/36 POs; 80 development, 40 held-out, eight baseline PDFs; 46 scans across the corpus; 12 layout families; 80 development oracles checked |
| Render configuration | YAML parses, web + worker + private PostgreSQL and secret env group present; no provider provisioning/account schema validation |

Docker's static build linter flags the public setting name `AUTH_MODE` as a possible secret because of its name. Its value is only `oidc`; no secret is embedded. An attempted MinIO test-image pull was refused by its registry. The completed storage smoke used a locally built filesystem-backed S3rver emulator instead. That tests object protocol/persistence, not AWS IAM, true encryption enforcement or production S3 availability. Initial container file-permission and emulator/proxy configuration failures were diagnosed and fixed before the passing final checks.

Early full-suite tests exposed three immutable-history insertion failures. Decision summaries are now finalized before insertion, and a stricter migration prohibits history updates altogether. The final full suite has no failing tests. Added regressions also cover conflicting duplicate review isolation and canonical identity preservation after blocked corrections.

## New measured development evaluation

Complete machine-readable reports are in [evaluation/completion-development](../evaluation/completion-development/). Existing synthetic-v2 reports and held-out expected answers were not overwritten. No new held-out parser/prompt tuning or live Gemini execution occurred. Each report records its actual source hashes, seed, document hashes, policy hashes, dirty working-tree status and runtime provenance. Extraction and financial reports can have different source revisions; consult their recorded hashes. The final worker report's application source fingerprint is `c8d02b0c5d4308126161c7161d8ab7b072a35be6cb3bce4f66663ee32b7c9820`.

| Mode | Measured result |
|---|---|
| PDF-to-field fallback | **1,472/1,616** present expected fields correct; **7** wrong and **137** missing; **85/1,479** populated proposals classified unsupported by the independent scorer; 79 backend-unverified proposals; **14/14** absent fields correctly left empty; 0 technical failures / 80 submissions |
| Gold-field financial engine | **80/80** decisions, vendor matches, PO matches, commitment effects, allocations, before/after balances and replay checks correct; **1,502/1,502** expected rules correct; review **18/80**; 0 technical failures |
| Full PDF-to-worker fallback | **60/80** final decisions match the independent oracle; review **33/80**; **63/80** commitment effects and **60/80** after-balances match the oracle; **80/80** replay checks; 0 technical failures |

All three modes were actually executed; their owned disposable databases were cleaned up (zero remaining). Worker mode executed real OCR, ingestion, worker processing and persisted decisions. Field correctness measures proposed values, including values that the backend marks unverified; correctness is not a permission to reserve funds. Unsupported-extraction counts include proposed values, not just financially trusted values. Do not present these development results as held-out or real-world extraction generalization.

The full pipeline has **20 oracle decision mismatches**, including 16 missed validations. It also records **one `unsafe_validations` mismatch**, retained honestly in the report: development group `development-group-063`, case `5fb87e983391861f`. The preceding scan `bbcbe87ca4f4a841` was incorrectly **BLOCKED** after PO extraction failed, and created no commitment. The final invoice requested USD 1,419.54 against actual remaining USD 1,608.81 and therefore passed actual balance/quantity checks; the oracle expects an overrun after assuming that preceding invoice validated. Actual remaining became USD 189.27. This is a material sequential extraction/decision discrepancy, not evidence that the engine exceeded its actual locked balance. Gold financial execution of the full sequence matches the oracle. Both the upstream failure and downstream mismatch remain counted; neither answers nor scores were changed to hide them.

Remaining failures include missing/incorrect OCR facts, unfamiliar layout evidence, ambiguous PO references and consequent review/blocked outcomes. Conservative fallback remains limited. Live Gemini might change results, but no improvement is claimed without running it.

## Functionality demonstrated

- Freshly generated PDFs process without filename-specific decisions. Valid digital and real scanned examples validate.
- Exact byte replay adds no run/commitment; re-exported business duplicates receive separate blocked assessments. Conflicting duplicate reviews cannot alter/release the original reservation.
- Missing numbers require review. Review corrections save human attribution/comment, retain prior immutable decisions, and execute all financial checks. Source confirmation never disables business rules.
- Existing commitments become HELD during review; successful revalidation releases/replaces atomically; blocked corrections preserve the old identity and hold. Explicit rejection creates an actual BLOCKED disposition event and releases only unsettled capacity. Settled commitments are not released by review.
- Partial invoices accumulate, overbilling blocks, and concurrent workers cannot exceed current authorization or create duplicate consuming commitments.
- Provider-contract failures use conservative fallback. Corrupted stored bytes fail technically without a decision/commitment. Worker leases, stale-owner rejection and explicit retries are tested.
- Dashboard counts exclude duplicate assessments from canonical invoice outcomes; runs/submissions are separate. Events shown in timelines and audit are stored records.

The dedicated demo workspace has 16 completed runs and 15 unique/unresolved invoice records: 12 VALIDATED, one NEEDS_REVIEW and two BLOCKED, plus one duplicate assessment recorded separately. It contains eight baseline partials and eight example submissions. Those counts are actual persisted records, not UI constants. The legacy workspace's 10 documents/five commitments were preserved, and repeating the new seeder changed no financial counts.

## Migrations and implementation files

Existing migrations 0001–0003 and regression inputs are preserved. Added:

- `0004_review_auth_audit.py`: membership, review tasks/corrections, audit events and worker heartbeats.
- `0005_immutable_audit_history.py`: database triggers protecting history.
- `0006_strict_history.py`: prohibit all updates/deletes of committed audit/revision/decision/correction rows; decisions are inserted once with final summaries.

Backend implementation files added/updated: `app/auth.py`, `audit.py`, `storage.py`, `operations_api.py`, `review/api.py`, `review/service.py`, `config.py`, `db.py`, `models.py`, `main.py`, `ingestion.py`, `upload_limit.py`, `workflow_api.py`, `worker/main.py`, `validation/engine.py`, `extraction/sourcefacts.py`, `fallback.py`, `evidence.py`, `pdf.py`, `gemini.py`; `pyproject.toml`, `uv.lock`; `demo/procurement.json`; `scripts/seed_workspace.py`, `provision_access.py`, `browser_regression.py`, `dataset_v2/isolation.py`; `tests/conftest.py` and `tests/application/{conftest,test_review,test_safeguards,test_security,test_storage,test_layouts}.py`.

Frontend implementation files added/updated: `src/{App,InvoiceWorkflow,main,auth,ui}.tsx`, `client.ts`, `styles.css`, `pages/{Dashboard,Reviews,PurchaseOrders,Audit}.tsx`; component regressions, `e2e/{complete,foundation,workflow}.spec.ts`, `vite.config.ts`, `playwright.config.ts`, `package.json`, `package-lock.json`.

Delivery configuration/documentation: root `Dockerfile`, `.dockerignore`, `.env.example`, `README.md`, `.github/workflows/ci.yml`; `deploy/render.yaml`, `deploy/README.md`; `docs/implementation-plan.md`, this verification document and `docs/demo-guide.md`; new development reports/verification receipts. Most source was already untracked in the supplied checkout, so `git diff --stat` alone does not enumerate the implementation. No commit was created.

Completed routes/screens: Overview dashboard, Process Invoice, `/runs/:id` Decision Details, Exception Review queue/details, Purchase Orders list/details and Audit History. API endpoints cover health/config, identity/workspace, vendors/POs/details, upload/authenticated source download, run history/details/retry/request-review, review queue/details/claim/corrections/rejection-release, dashboard and audit history. See runtime OpenAPI `/docs` for exact schemas.

## Commands actually executed

From `backend`: `uv add` for JWT/crypto and boto3; `alembic upgrade head`; `alembic current`; `alembic check`; `python -m scripts.seed_workspace --process-examples` (and safe repeat); `ruff check app tests migrations scripts`; `ruff format --check app tests migrations scripts`; `pytest -q`; `python -m scripts.browser_regression`; `python -m scripts.validate_dataset_v2`; `python -m scripts.evaluate_dataset_v2` for extraction/gold/worker with development/fallback and new report paths. Commands used the project's `.venv/bin` executables during verification. Python/SQL checks compared legacy record IDs/commitments and service-restart history.

From `frontend`: `npm install react-router-dom @auth0/auth0-react`; `npm test`; `npm run build`; Playwright/Chromium browser workflows and direct route/error inspection. Services were launched with Uvicorn on all interfaces, `python -m app.worker.main`, and Vite with `VITE_HOST=0.0.0.0` using the real backend proxy. Docker Compose PostgreSQL was running and healthy. Docker image builds and an isolated owned-database/S3-emulator container smoke were executed; test containers/databases were removed afterward. Running local demonstration services are retained in this cloud session; their lifetime depends on the session.

## Opening the interactive website

**There is no browser-accessible website URL yet.** The environment-status API reports `capabilities: []`; no browser preview, right-side web panel or forwarded-port tool is available in this task. Cloud loopback and private interface addresses cannot be opened directly from a laptop. No screenshot, archive or fabricated URL is offered as a substitute.

The [README](../README.md) gives reproducible own-computer launch instructions. For a real HTTPS demonstration, approve publishing the reviewed source and creating the prepared Render web/worker/PostgreSQL resources with Auth0 and private S3. Current service plans/costs require owner review. Provider credentials, private environment settings and outbound host permission are required; never paste keys into chat.

After that approved deployment, record and verify the provider-assigned HTTPS web address, configure that exact origin in Auth0, provision individual owner/evaluator workspace memberships and perform real login/upload checks. The user then opens that verified HTTPS address and signs in with their invited account. [deploy/README.md](../deploy/README.md) contains the precise provider UI steps and credentials/configuration checklist. This release step is the only remaining route to a remotely interactive website in this environment.

## Remaining limits

No live Gemini key is configured; adapter tests pass but live extraction is pending. Auth0 live login, real AWS permissions/encryption, Render provisioning/public HTTPS, and evaluator invitations are untested external release checks. No actual payment/settlement execution exists. English OCR, positive invoices, supported currencies and the documented zero-overrun policy define the supported scope; nonzero header adjustment allocation and unsupported accounting policies require review. UI lists/operational queries suit demo volume, and large-scale optimization is not claimed. Calendar-2026 synthetic PO dates need new catalogue records for later-year demonstrations. The fallback evaluation shortcomings above remain visible; the application is functional, not a claim of perfect autonomous extraction.
