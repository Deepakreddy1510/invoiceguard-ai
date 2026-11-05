# Premium experience verification

Executed 6 November 2026 (Asia/Calcutta) against the premium experience source revision. This report covers actual local commands; the publishing response supplies the resulting commit and GitHub Actions URL/conclusion.

## Executed checks

| Check | Actual result |
| --- | --- |
| Backend `pytest -q` | **251 passed**, 0 failed, 1 upstream Starlette/httpx deprecation warning, 88.85 seconds |
| Backend Ruff lint and formatting | Passed; 106 Python files already formatted |
| Frontend `npm test` | **36 passed**, 0 failed |
| Frontend ESLint / TypeScript / Prettier | All passed |
| Frontend production build | Passed |
| Real-service Playwright | **15 passed**, 0 failed, 0 skipped; 2.0 minutes |
| Migration preservation and Alembic schema check | Passed within backend suite, including real persisted invoice/reservation and retained email events |
| Frozen dataset integrity | 18 vendors, 36 POs, 80 development PDFs, 40 held-out PDFs, 8 baseline PDFs; **128 hashes verified**, 80 development oracles checked; 46 scans, 12 layout families |
| Production Docker build | Passed; image `invoiceguard-ai:premium-experience` |
| Gitleaks 8.24.3 | Passed; zero findings across 396 publication source files, approximately 5.32 MB |
| Publication diff | `git diff --check` passed; no changes to original fixtures, frozen datasets, evaluation answers, compose mapping or CI validation steps |

Backend suite invocation used a newly generated `ig_premium_<uuid>_test` database and removed only that invocation-owned database. The browser runner similarly creates its own databases, documents and API/worker/Vite processes. Neither uses the working demonstration database.

Commands executed from `backend`:

```sh
.venv/bin/ruff check app tests scripts migrations
.venv/bin/ruff format --check app tests scripts migrations
# A create-only UUID database harness supplied TEST_DATABASE_URL to this subprocess:
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.validate_dataset_v2
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m scripts.browser_regression
```

Commands executed from `frontend`:

```sh
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

Docker used the local daemon with explicit socket selection and the session CA bundle as a BuildKit secret, following cloud runtime instructions. BuildKit emitted its existing name-based `AUTH_MODE` warning; that variable holds an authentication mode, not credentials. No Dockerfile weakening or TLS bypass was introduced.

The secret scan used the existing rule configuration against tracked plus new nonignored publication files. Ignored `.env`, local databases, private credentials, screenshots, logs and dependency directories are excluded from publication. This is a source scan, not a claim of rotating or validating external credentials. The CI workflow itself is unchanged, including real service tests, process-group cleanup and disabled uv caching.

## Visual and accessibility report

Real browser screenshots were generated for eight routes (Overview, Process, Email Intake, Vendors, Purchase Orders, Reviews, Settings, Activity) at **1920, 1440, 1280, 1024, 768 and 390 CSS pixels**: 48 page screenshots. The suite also captures the actual focused email dialog at six widths, Asterfield Overview at desktop/mobile and Overview at 150% rendered CSS zoom. Existing processing/PO screenshots remain generated. Artifacts live in ignored `frontend/test-results/`; they contain synthetic test records only.

Automated assertions cover page overflow, loaded headings, accidental object rendering, empty rules and duplicate prototype branding. Axe WCAG A/AA scans pass on all eight routes, Asterfield Overview and the focused email dialog. Native modal Tab containment and Escape closure are exercised in Chromium. Reduced motion is implemented in CSS. This is automated coverage, not a blanket accessibility certification; Windows native browser zoom, assistive technology and live provider accounts still require user-side checks.

Manual inspection of generated desktop/mobile Overview, processing and email screenshots guided fixes to selected-row contrast, muted text, link affordances and decision placement. Final desktop Asterfield Overview and email dialog were inspected after those corrections: the dashboard uses actual 20 unique invoices, the inbox card has honest disconnected/empty guidance, and the dialog places Blocked, its real reason and next action above document fields. Narrow tables remain bounded/scrollable rather than widening the page.

## Regression and financial integrity

All earlier browser workflows remain: original PDF processing, review/revalidation, procurement edits/imports, real worker decisions, provider-mocked Gmail intake and Asterfield replay. The browser runner timeout grows from 120 to 300 seconds to accommodate the expanded visual checks; no validation is skipped or marked continue-on-error.

The Asterfield installer runs only in the disposable browser database. Existing Asterfield source assets and original regression fixtures are unchanged: **18 vendors, 36 POs, 21 documents, 14 validated / 6 blocked / 1 review document decisions**. One duplicate document is excluded from the canonical dashboard; therefore it shows **20 unique invoices, 14 validated / 5 blocked / 1 review**. Replays and manual reviews do not inflate unique counts or reservations.

`backend/app/validation/engine.py` is unchanged (SHA-256 `f61250c319ad33e4457d6f4ffbcdaf35b5dbc9160a48b5728751408c05337072`). Currency arithmetic, commitment rules, duplicate policy and procurement remain unchanged. The new PO Result column reads recorded rule outcomes and distinguishes current balances from historical decisions.

Workspace tests cover target-specific ADMIN access, forbidden reviewer/viewer actions, concurrent version conflicts, immutable IDs/retained records, archive confirmations, last-active protection, live job/mailbox conflicts, paused queue/financial writes, restored processing, preserved audit noise in raw view and queued token-revocation cleanup without mailbox reads. Browser lifecycle tests confirm the same purchase-order response before and after rename/archive/restore.

An initial attempt against an old disposable test database exposed schema drift: the nullable email-event evidence column was absent despite its migration stamp. The final migration conditionally repairs that missing column when upgrading from 0008. Its new preservation test explicitly reproduces this drift and compares all historical financial/event records before and after the upgrade. Final full-suite measurements above use a fresh owned database, not a reset of that stale database or the demo.

## Changed files

- Shared UI: `frontend/src/{premium.css,Experience.tsx,OverviewInsights.tsx,TechnicalDetails.tsx,App.tsx,main.tsx,auth.tsx,workspaces.tsx,business.ts}`.
- Workflow components: `InvoiceWorkflow.tsx`, `RunDetails.tsx`, `POComparison.tsx`, `POEditor.tsx`, `ProcurementImport.tsx`.
- Pages: `Dashboard.tsx`, `EmailIntake.tsx`, `Reviews.tsx`, `Vendors.tsx`, `PurchaseOrders.tsx`, `Audit.tsx`, new `WorkspaceSettings.tsx`.
- Frontend tests: new `premium.test.tsx`, updated `EmailIntake.test.tsx`, `business.test.tsx`, `test-setup.ts`; new `e2e/premium.spec.ts` and updated original complete/email/foundation/product/workflow/Asterfield browser tests.
- Backend lifecycle/retained activity: `app/{models.py,audit.py,auth.py,workspaces_api.py,operations_api.py,worker/main.py,email_intake/service.py}`, migration `0009_workspace_lifecycle.py`, new `test_workspace_lifecycle.py` and `test_lifecycle_migration.py`.
- Test harness: `backend/scripts/browser_regression.py` timeout only.
- Documentation: README links, this report and `premium-experience.md`.

## Limits and remaining verification

No live Gemini, live Gmail, Auth0, S3 or Render verification is claimed. Provider mocks exercise real ingestion, worker, PostgreSQL and financial decisions but do not prove delivery from a live mailbox. Source-grounded rule summaries are deterministic; no new generative narrative adapter is claimed. Synthetic PDFs do not establish real-world extraction generalization. External reference design sites were blocked by network policy.

No deployment, paid purchase, financial-policy change, procurement regeneration, demo reset or credential publication is part of this release. The application remains subject to the existing positive-invoice/currency/tax scope described in README. See [safe Windows instructions and remaining provider setup](premium-experience.md).
