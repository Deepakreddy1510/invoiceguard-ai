# Phase 2 implementation and executed verification

Executed 2026-11-01. No commit, publication or deployment. Phase 1 files, initial migration and original test coverage were preserved. Live Gemini acceptance remains pending credentials; do not read the fallback results as live-provider verification.

## Delivered behavior

2A: bounded multipart PDF upload (10 MiB file, bounded total body), signature/readability/encryption/page/render limits, private local document storage, SHA-256 replay, idempotency key conflicts, persistent submissions/runs/events, PyMuPDF text extraction, Tesseract English OCR with geometric column splitting, strict Gemini REST adapter and schema, source-linked field verification, conservative fallback and explicit unknowns.

2B: vendor identity/approval, vendor–PO ownership, PO existence/status/dates, explicit currency and pricing modes, required fields, finite decimal/minor-unit checks, subtotal/tax/gross arithmetic, source-supported item matching/pricing/tax/quantity, duplicate and near-duplicate assessment, partial invoicing, locked amount/quantity capacity checks and atomic decision/reservation/event finalization. Decisions never execute payment. Unsupported/uncertain facts require review; technical failures have no business decision.

2C: upload, actual event timeline, extracted header/line details and quotes, source PDF access, matched PO and balance explanation, rule results, business outcome, run IDs/timestamps, persistent paginated history and failed-run retry. Polling reads stored records and never simulates stages. Browser reload reconstructs the selected run from its URL.

The worker uses short PostgreSQL transactions to claim work with SKIP LOCKED, a 180-second lease and ownership token, at most three automatic interrupted-attempt claims, and stale-worker fencing. PDF/OCR subprocess work and external model calls occur outside database transactions. Explicit retries create child runs and preserve failures. A finalization transaction locks the run and affected PO and serializes business identity; decisions and consuming commitments commit together. No Redis or extra service framework was introduced.

## Database changes

- `0001_initial.py` retained.
- `0002_documents_runs_events.py`: invoice_documents, document_submissions, processing_runs and run_events.
- `0003_decisions_commitments.py`: invoices, invoice_revisions, decisions, financial_commitments and commitment_allocations.
- Workspace/hash and submission/idempotency uniqueness; canonical vendor/invoice-number identity; one decision/revision per run; one consuming commitment per invoice through a partial unique index; positive finite commitment/allocation constraints; indexed work claiming/events/PO consumption.
- Procurement schema remains compatible. Finalization uses the documented transaction protocol; cross-row cumulative totals cannot be protected by a CHECK constraint alone.
- Commitment states include RESERVED, HELD, RELEASED and SETTLED; Phase 2 creates reservations. Reviewer replacement/hold/release actions and optional external settlement are not exposed yet.

## Actual final test results

| Check | Executed result |
|---|---|
| Complete Pytest suite | **58 passed, 0 failed**: original 14 plus 44 Phase 2 cases |
| Frontend Vitest | **4 passed, 0 failed**: original 2 plus 2 failure/queued/retry UI tests |
| Playwright Chromium | **6 passed, 0 failed**: original procurement check plus 5 real workflow browser tests |
| TypeScript + production Vite build | Passed |
| Ruff lint and formatting | Passed |
| Alembic drift check | No new upgrade operations |
| Phase 2 downgrade to 0001 and upgrade to head | Passed on isolated test database |
| API/worker real process restart | Four runs and 40 events compared identically after restart; two business invoice identities, not four |
| Normal demo startup/upload | Real digital PDF reached VALIDATED, ten persisted events; fallback provider |

The total is 68 distinct passing tests, not a sum of reruns. No tests were skipped to obtain these counts. GitHub Actions was updated but not run remotely.

## Edge-case evidence

| Scenario | Executed outcome |
|---|---|
| Valid digital invoice, USD 550 | VALIDATED; one reservation |
| Real scanned invoice, independent identity/amount | VALIDATED; OCR execution persisted and shown in browser |
| Exact bytes under another filename/key | Existing run returned; no second financial consumption |
| Same vendor/invoice number, re-exported bytes | BLOCKED duplicate assessment; canonical invoice/commitment retained |
| Conflicting facts for an existing identity | Review policy in engine; broader variants remain Phase 3 regression scope |
| Same vendor/date/amount, different invoice number | NEEDS_REVIEW near-duplicate; no new reservation |
| Missing invoice number | NEEDS_REVIEW with specific required-field result |
| Independent PO partial sequence: 880, 770, 660 against 2,200 | VALIDATED, VALIDATED, BLOCKED; 550 remains before third, excess 110 |
| Competing concurrent partials | One VALIDATED, one BLOCKED; total stays within authorization |
| Concurrent same business invoice | One commitment only |
| Closed/missing PO, mismatched vendor, suspended vendor, excessive unit price | BLOCKED with applicable rule |
| Incorrect arithmetic, unsupported/ambiguous dates, unverified total | NEEDS_REVIEW; no commitment |
| Corrupt/encrypted/over-page-limit/oversized document | Rejected; no financial consumption |
| Model timeout/auth/rate-limit/malformed output | Adapter error contracts tested; fallback exercised without invented fields |
| Tesseract timeout | Explicit extraction failure tested |
| Lost document artifact | Worker FAILED with no decision; restoring artifact and retry succeeds |
| Interrupted worker lease | Reclaimed run completes; prior ownership token cannot write |
| Finalization exception before commit | No decision/commitment survives rollback; retry finalizes safely |
| Lost commit acknowledgement during ingestion | Stored PDF retained rather than deleting a possibly committed artifact |

## Commands executed

From backend unless stated otherwise:

- `uv add 'pymupdf>=1.25,<2' 'python-multipart>=0.0.20,<1' 'httpx>=0.28,<1'`; Pillow was initially added, then removed because PyMuPDF already renders synthetic scans.
- `uv run alembic revision --autogenerate -m documents_runs_events --rev-id 0002`; corresponding revision command for 0003; `uv run alembic upgrade head`.
- `uv run pytest tests/phase2/test_extraction.py tests/phase2/test_ingestion.py -q` for 2A; financial/transaction suites for 2B; API and browser suites for 2C; `uv run pytest -q` for complete regression.
- `uv run alembic check`; isolated test DATABASE_URL with `uv run alembic downgrade 0001` then `uv run alembic upgrade head`.
- `uv run python -m scripts.generate_samples`; `uv run python -m scripts.generate_heldout`; `uv run python -m scripts.evaluate_extraction`.
- Docker Compose `createdb` for a separate invoiceguard_e2e database; its DATABASE_URL with `uv run python -m scripts.reset_test_database`.
- `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`; `uv run python -m app.worker.main`; frontend `npm run dev -- --port 5173 --strictPort`.
- Frontend `npm run build`; `npm test`; `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e`.
- Ruff check/format for app/tests/scripts/migrations and `git diff --check`.
- Real HTTP uploads/readiness/history queries, bounded outcome polling, exact before/after comparison after terminating/restarting only task-owned API/worker processes.

Use README for complete repeatable startup and test commands. End-to-end suites require a clean isolated database; do not reset the normal demo. Current handoff services use the regular invoiceguard database with a real synthetic VALIDATED example; test history remains separately persisted in invoiceguard_e2e.

## Extraction evaluation and failures corrected

A separate renderer created three manually labeled, multi-column/multi-page fixtures, including a scan and a missing number. Expectations were not supplied to extraction. Initial fallback evaluation recovered **0/23 present fields** because sorted text merged columns. The initial result is retained in `measured-fallback-initial.json`.

Correction preserved digital blocks and used OCR word coordinates to split large column gaps. Compound-label values now cause abstention. Post-correction evaluation recovered **23/23 present fields**, correctly abstained on **1 missing field**, routed **1/3 invoices to review**, and recorded **0 technical failures**. These are now regression fixtures because they informed a fix. They are too small and insufficiently independent for a general accuracy claim. No live Gemini extraction metric was measured.

Other failures found and fixed included Decimal/string balance subtraction, a missing OCR TSV invocation, line-item quote substring ambiguity, and TypeScript test option mismatches. Final checks above passed after correction. A nonblocking Starlette TestClient/httpx deprecation warning remains; no warnings were suppressed.

## Exact Phase 2 file inventory

Modified:

- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `README.md`, `docs/implementation-plan.md`.
- `backend/pyproject.toml`, `backend/uv.lock`.
- `backend/app/config.py`, `backend/app/main.py`, `backend/app/models.py`.
- `frontend/src/App.tsx`, `frontend/src/styles.css`.

Created:

- `backend/app/ingestion.py`, `backend/app/upload_limit.py`, `backend/app/workflow_api.py`.
- `backend/app/extraction/__init__.py`, `schema.py`, `pdf.py`, `fallback.py`, `gemini.py`, `evidence.py`, `pipeline.py`.
- `backend/app/validation/__init__.py`, `engine.py`; `backend/app/worker/__init__.py`, `main.py`.
- `backend/migrations/versions/0002_documents_runs_events.py`, `0003_decisions_commitments.py`.
- `backend/scripts/__init__.py`, `generate_samples.py`, `generate_heldout.py`, `evaluate_extraction.py`, `reset_test_database.py`.
- `backend/tests/phase2/conftest.py`, `test_extraction.py`, `test_ingestion.py`, `test_financial.py`, `test_transactions.py`, `test_api.py`.
- `frontend/src/InvoiceWorkflow.tsx`, `frontend/src/InvoiceWorkflow.test.tsx`, `frontend/e2e/workflow.spec.ts`.
- `samples/README.md`; `samples/invoices/valid.pdf`, `valid-alternate.pdf`, `valid-scanned.pdf`, `duplicate-reexported.pdf`, `missing.pdf`, `partial-1.pdf`, `partial-2.pdf`, `overbilling.pdf`.
- `samples/extraction/heldout-digital.pdf`, `heldout-scan.pdf`, `heldout-missing.pdf`, `manifest.json`, `measured-fallback-initial.json`, `measured-fallback-regression.json`.
- `docs/phase-2-verification.md`.

Private generated uploads, restart snapshots and test artifacts are ignored under `.local`/test output directories, not application source. Phase 1 changes were already uncommitted at the start; no commit was made here.

## Remaining limitations and Phase 3 handoff

- **Live Gemini is unverified:** no configured key exists in runtime metadata or checked process bindings. Set GEMINI_API_KEY securely and allow generativelanguage.googleapis.com; restart the worker and execute real-provider extraction on independent layouts. MockTransport verifies request/schema/error handling only.
- Local unauthenticated synthetic development only. Hosted evaluator access still requires the Auth0 plan before deployment.
- Automatic financial validation requires explicit source labels and one attributable item row. General table layouts can be extracted by Gemini but stay review-only if evidence cannot be independently verified. Ambiguous date/currency formats, nonzero header adjustments, mixed taxes and credit notes require review.
- OCR verification establishes consistency with OCR text, not guaranteed correspondence to image truth. Expand low-quality scan evaluation and uncertainty routing.
- One selected PO/currency; no goods receipts, FX, payment, credit application or jurisdictional tax compliance.
- Event attempts are preserved; extraction fields on a reclaimed run reflect the latest attempt. Versioned per-attempt artifacts/raw provider outputs are future work. Explicit child retry runs retain the original run's fields/events.
- Full correction/replacement/hold/release workflows and external settlement are not exposed. No force-validation override exists.
- The local file store and database need joint backups; a commit-acknowledgement failure may leave an orphan artifact for later reconciliation. Worker restart/supervision is still required for sustained database outages.
- Expand stable currency metadata, cross-entity constraint defense, business-identifier variants, tax-inclusive/rounding limits and broader held-out coverage. Current explicit process restart, lease fencing, race and rollback checks do not establish enterprise availability.

Stop after Phase 2 review; no Phase 3 implementation or hosting was started.
