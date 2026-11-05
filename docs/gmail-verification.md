# Gmail intake implementation and verification

This change extends base revision `2427b8956c038e7e77f758964e8c51133646beb8`. It does not deploy the application or activate paid infrastructure. The original demonstration Docker volume was never mounted; database work used the separate verification PostgreSQL project, a newly created `invoiceguard_gmail_test` database and ownership-checked disposable browser/migration databases.

## Actual completed local checks

| Check | Actual result |
|---|---|
| Full backend pytest | **187 passed, 0 failed**, including all 138 pre-existing regressions and 49 Gmail/security/intake cases |
| Frontend Vitest | **28 passed, 0 failed**, including all 25 previous cases |
| Real-service Playwright | **12 passed, 0 failed**, including all 11 previous scenarios and the new provider-mocked Gmail browser case |
| Backend Ruff formatting/lint | Passed; final formatting check reports 100 files formatted |
| Frontend Prettier, ESLint, TypeScript | Passed |
| Production frontend build | Passed |
| Additive schema migration | Fresh migration 0008 and migration-preservation/model-drift regression passed |
| Financial-engine integrity | Unchanged SHA-256 `f61250c319ad33e4457d6f4ffbcdaf35b5dbc9160a48b5728751408c05337072` |
| Synthetic smoke PDF command | Generated three PDFs in an ignored new directory; no database/mailbox access |
| Resource-unavailable path | Actual digital PDF reading passed with Unix `resource` import unavailable; **not** native Windows verification |
| Secret scan | Gitleaks 8.24.3, existing detector configuration, zero source-inventory findings |
| Live Gmail | **UNVERIFIED** — no real Google OAuth/mailbox interaction observed |
| Live Gemini | **UNVERIFIED** — provider tests used mocked responses only |

The backend warning is the existing upstream Starlette/httpx TestClient deprecation. Browser output also includes inherited Node color-environment warnings. These are not hidden failures. Early development failures in heading screening and a Gemini branch variable were corrected; no original expected financial outcomes or tests were weakened.

Commands actually executed: `uv lock`; Ruff format/check; `TEST_DATABASE_URL=.../invoiceguard_gmail_test .venv/bin/pytest -q`; frontend `npm run format`, `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`; and `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m scripts.browser_regression`. Credentials were absent from these commands except the existing publicly documented disposable PostgreSQL development password. Real provider secrets were not configured or committed.

Playwright emits GitHub annotations in Actions as well as its full list reporter, so failed assertions are directly reviewable without weakening tests.

The GitHub Actions workflow retains backend checks, schema drift checks, frontend tests/build, real-service browser tests, production Docker build and reliable post-job cleanup. It is unchanged by this feature. The delivery response reports the observed run conclusion after publication; local results are not a substitute for that remote run.

## Implemented capability and evidence

**Connection foundation:** real confidential Google OAuth code exchange, PKCE, single-use state/cookie/user/workspace binding and expiration, callback membership revalidation, exact trusted-origin checks, encrypted workspace-bound access/refresh credentials, refresh/reconnect, queued revocation and disconnect. The UI receives safe availability/account/status information only. OAuth callback query logging and Gmail HTTP resource-ID logging are suppressed without hiding persisted operational failures.

**Automatic intake:** current-history baseline without old-mail import; bounded INBOX polling by the existing worker; persistent cursor/page token; recent-only stale-history recovery; committed-prefix continuation; mailbox/attachment advisory locks; restart recovery; bounded queues and retry backoff; Google 429 and quota-related 403 handling; no HTTP-lifecycle mailbox synchronization. No Pub/Sub or additional queue service is introduced.

**Intelligent screening:** normalized plain/HTML email text, bounded MIME tree/body/attachment sizes, per-attachment Gemini structured schema with verified quotes and explicit fallback, invoice/quotation/brochure/uncertain distinctions, multiple-invoice-PDF review, candidate values and source provenance. Unknown information is omitted. Sender address is a candidate, never vendor identity authorization. Links/resources inside messages are not followed and attachments are not executed.

**Financial safety:** accepted bytes use the existing verified storage/ingestion/worker path. Handoff IDs are committed atomically before worker claim. `email-po-review-v1` records email evidence separately and can require additional review; it cannot authorize a reservation or override a confirmed financial violation. It persists through retries, extraction-mode comparisons and financial review revisions. Existing PDF-only behavior remains covered by the original regressions.

**Operator UI:** warm-design Email Intake navigation/page, configuration/unavailable state, connect/reconnect/disconnect/check controls, actual persisted metrics, search/filter/pagination, safe email body and original-PDF preview, source facts/quotes, PO candidates, classification model/fallback reason, intake disposition, linked current financial decision/rules/run events, original handoff links and attempt-specific intake history. Latest financial review revisions appear without rewriting original source run IDs or inflating unique invoice metrics.

**Human review:** attributed reasons, supported PO candidate selection, forward/ignore/retry controls. Confirmation only admits a PDF to financial processing. Unsupported files remain excluded; already processed financial history cannot be erased by intake review. Prior classification and review snapshots survive retries.

The browser contract fixture is explicitly labeled **provider-mocked**, lives under `backend/tests/`, is excluded by the existing Docker ignore policy, and refuses ordinary application databases or hosted runtime settings. It runs the real Gmail adapter through HTTP mock transport, then persists actual source identities/PDF handoff. Separate API/worker/Vite processes and PostgreSQL produce the visible decisions. No production simulation endpoint or pretend email arrival is added.

The browser scenario created an isolated custom workspace and procurement, accepted an actual PDF requesting **USD 66**, observed VALIDATED and **USD 154** remaining from a **USD 220** PO, then observed BLOCKED for a **USD 176** invoice with no extra consumption. It verified source evidence, provider labels, actual persisted stages, rules, reload persistence and workspace isolation; automated WCAG A/AA scanning reported no violations on that view. This is synthetic regression evidence, not extraction generalization or live Gmail delivery evidence.

## Configuration, provider setup and limits

See [Gmail setup and Windows CMD instructions](gmail-intake.md) for every new variable, exact OAuth client/test-user/redirect setup, the restricted read scope, seven-day Testing-token limitation, public-production verification/security-assessment considerations, live smoke-test steps and deployment prerequisites. Email Gemini use is explicitly off by default and needs both `GMAIL_USE_GEMINI=true` and the existing server Gemini key.

Native Windows execution, production Auth0/S3 integration, Google production verification/security assessment and live Gmail/Gemini calls were not performed. The implementation includes the Windows timezone dependency and guarded Unix resource caps, with the original subprocess/page/pixel limits still in place. One worker performs bounded mail work alongside invoice jobs; no throughput/SLA is claimed. No full-mailbox historical backfill, automatic PO amendments, general AI financial approval, or arbitrary attachment formats are introduced. Disconnect stops reads/revokes credentials while retaining historical evidence and decisions.

## Files created or modified

- `.env.example`
- `README.md`
- `backend/app/config.py`
- `backend/app/email_intake/__init__.py`
- `backend/app/email_intake/api.py`
- `backend/app/email_intake/google.py`
- `backend/app/email_intake/policy.py`
- `backend/app/email_intake/screening.py`
- `backend/app/email_intake/service.py`
- `backend/app/extraction/pdf.py`
- `backend/app/ingestion.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/review/service.py`
- `backend/app/worker/main.py`
- `backend/app/workflow_api.py`
- `backend/migrations/versions/0008_gmail_intake.py`
- `backend/pyproject.toml`
- `backend/scripts/dataset_v2/isolation.py`
- `backend/scripts/generate_gmail_smoke_samples.py`
- `backend/tests/application/test_gmail.py`
- `backend/tests/browser_email_fixture.py`
- `backend/tests/conftest.py`
- `backend/uv.lock`
- `docs/gmail-intake.md`
- `docs/gmail-verification.md`
- `frontend/e2e/email.spec.ts`
- `frontend/src/App.tsx`
- `frontend/src/EmailIntake.test.tsx`
- `frontend/src/RunDetails.tsx`
- `frontend/src/models.ts`
- `frontend/src/pages/EmailIntake.tsx`
- `frontend/src/styles.css`
- `frontend/src/ui.tsx`

- `frontend/playwright.config.ts` (GitHub annotation reporter; all tests/assertions retained)

## CI browser follow-up

The first published run failed in its browser step. Exact CI reproduction exposed a source-recognition difference in the existing six-page OCR scenario: generated identifier `UI-EDITORIAL-MW3IE5TY` was read as `UI-EDITORIAL-MWSIESTY`. The Gmail browser scenario passed. The OCR integration fixture now uses deterministic `UI-EDITORIAL-FRESH` within the suite's fresh database. Every exact identifier, OCR, financial, event and historical assertion remains enabled; no production parser or financial rule was changed. This documents an OCR accuracy limitation, not extraction-generalization success.

- `frontend/e2e/redesign.spec.ts` (deterministic OCR fixture identifier; existing assertions retained)

After the deterministic fixture change, the exact GitHub Actions browser shell passed all 12 cases locally with `CI=true`, real services and process-group cleanup. OCR character recognition remains a known limitation; verification of an OCR quote does not independently prove every rendered character was recognized correctly. No financial confidence rule or parser correction was introduced.

The final safety regression covers a Gmail AUTO handoff of the same bytes previously validated under FALLBACK. The comparison run retains the current email context, routes a conflicting PO claim to financial review, preserves the original decision and keeps exactly one consuming 550-unit commitment. Ordinary manual mode comparisons still inherit their prior context.
