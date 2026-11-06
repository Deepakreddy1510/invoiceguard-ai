# Exception Review and invoice identity verification

Verified on 6 November 2026, starting from `ccc28e90656ccf9880e126317a472925801e9636`. This release fixes Exception Review, applies consistent invoice identity/status presentation and refines existing workbenches. No deployment, payment execution, database reset or Asterfield reseed was performed.

## Root cause and correction

Two incompatible layout modes combined on `/reviews`. The legacy `.queue-only .review-queue` used a three-column grid for cards **and pagination**. The later `.review-layout` rule constrained its parent queue column to 260 px. The review page did not automatically select an eligible record, so the detail area was absent. A genuine `RC-261111` record reproduced a card only **75.3 px** wide at a 1920 px viewport, with wrapping identifiers, overlapping pagination and an empty right side.

The replacement `.review-workbench` has explicit named grid areas and does not use either conflicting root class. Queue, detail and PDF are separate children, in that order. At 1920 px the actual columns measured approximately **387 / 653 / 532 px**, satisfying the requested proportions. The first open/revalidating review is selected when there is no explicit selection. Polls, tab changes and queue filters preserve manual selection; polling does not discard drafts. Failed/missing selections display a recoverable error.

- At 1600 px and wider: queue, correction workspace, private PDF reader.
- At 651–1599 px: queue and details; Document tab provides the real source PDF.
- At 650 px and below: explicit queue/detail navigation, full readable detail and document access.
- Queue toolbar and pagination sit outside its bounded, focusable scroll region. Details have a separate named scroll region. Mobile detail uses normal scrolling.

## Invoice identity and status

`InvoiceIdentity` consistently uses a neutral document icon. Real invoice identifiers remain complete in accessible text and title attributes, ellipsize only in constrained rows and wrap in details. Copy actions use the original identifier. Unknown suppliers are identified honestly; no fake supplier name or shortened backend ID is generated.

Financial badges use green check-circle (Validated), amber alert-circle (Needs review) and red x-circle (Blocked). Processing uses a neutral progress symbol; technical failure uses a distinct error symbol and Processing failed. Technical completion remains Completed, without implying financial approval. Status labels cannot break within words in dense tables.

Overview attention rows show the actual supplier, actual amount/currency when available, recorded outcome and explicit Open action. The amount comes from actual run details because the summary endpoint does not provide it. The same identity conventions appear in the processing queue/detail, review queue/detail, email detail, invoice history and recent activity. Email subjects retain their actual identity and a neutral document marker; a filename is retained until an invoice number is known.

## Page behavior

| Page | Result |
| --- | --- |
| Overview | Normal page scrolling, compact attention rows, neutral identity, genuine totals/statuses, retained charts and activity. |
| Invoice Processing | Existing paginated workbench and live persisted stages retained; focusable queue and PDF scroll regions; audit guidance moves into Help. |
| Exception Review | Automatic eligible selection, server-backed search, independent scrolling, correction/checks/history/document tabs, evidence and error recovery. |
| Email Intake | Bounded keyboard-accessible inbox, sticky readable headers, selected row, retained focused dialog, long-subject wrapping, original evidence. |
| Vendors | Ten records per page, sticky headers, bounded table, readily accessible create/import and pagination. |
| Purchase Orders | Ten records per page, search/status filter, retained details/items/reservation balances and controls. |
| Settings | Active and archived workspace groups, retained rename/archive/restore, collapsible secondary email configuration, normal scrolling. |
| Activity | Shared invoice presentation; genuine event feed and administrator history retained. |

The **only production backend change** is an optional read-only `search` parameter on `GET /reviews`. It searches extracted invoice number, supplier name and PO reference before pagination, escapes SQL wildcard characters literally and retains workspace/status filters. Financial validation, processing, authentication, Gmail policy and all mutation contracts are unchanged. A pre-existing Gmail regression selected a PO by number without workspace scope; its test lookup is now explicitly scoped to the test user's workspace. The assertion and application policy remain intact.

## Actual checks

| Check | Final result |
| --- | --- |
| Backend pytest | 253 passed, 0 failed; one existing Starlette deprecation warning. |
| Frontend Vitest | 53 passed, 0 failed in 11 files. |
| Real-service Playwright | 19 passed, 0 failed; final PDF/native-zoom follow-up 3/3 and final mobile-email follow-up 1/1 also passed. |
| Backend Ruff lint/format | Passed. |
| Frontend ESLint/TypeScript/Prettier/build | Passed. |
| Migration/schema consistency | Actual migration and `alembic check` covered in backend tests; no new migration. |
| Production Docker image | Built successfully with TLS verification; no image deployment or registry publication. |
| Gitleaks | No leaks found in the complete tracked/proposed source snapshot, using existing detector rules. |
| Financial engine hash | Unchanged: `f61250c319ad33e4457d6f4ffbcdaf35b5dbc9160a48b5728751408c05337072`. |

Initial checks caught incorrect test-fixture assumptions (an unknown PO correctly blocks), the unscoped Gmail test lookup, a switch hit-target overlap and header contrast regressions. Those issues were corrected and the complete suites rerun; no test is skipped, softened or marked continue-on-error. The Asterfield navigation assertion now waits for the vendor route and scopes its supplier check to the supplier table, avoiding newly legitimate repeated labels on Overview. The genuine review fixture now uses source-supported unmatched line items and supplier ambiguities, with resolution through the existing rejection workflow.

All backend/browser data was created in newly owned UUID-named disposable PostgreSQL databases with temporary file storage. Existing demo databases, records, commitments and Gmail connections were not reset or inspected. Synthetic QA fixtures create independent one-review, multiple-review and empty workspaces; all outcomes/events come from actual ingestion, extraction and financial processing. No fake decisions or workflow events are inserted.

Commands executed include:

```sh
# frontend
npm run format
npm run lint
npm run typecheck
npm test
npm run build
npm run format:check
# backend (fresh owned test DB, TEST_DATABASE_URL injected by an isolated harness)
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests migrations scripts
.venv/bin/ruff format --check app tests migrations scripts
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m scripts.browser_regression
# production image, managed local Docker socket, existing combined CA secret
# docker build --secret id=ca_bundle,src=/etc/ssl/certs/ca-certificates.crt -t invoiceguard-ai:review-ux .
# gitleaks dir <tracked-and-proposed-source-snapshot> --config .gitleaks.toml --redact
```

Do not point regression fixtures at a working database. The existing browser runner owns and removes only its newly created database. Ordinary frontend unit tests mock API responses; browser tests use actual API/worker/PostgreSQL/PDF/OCR. Gmail transport remains explicitly mocked. Gemini is not called.

## Screenshots and responsive inspection

Actual Chromium screens were captured and inspected at **1920, 1440, 1280, 1024, 768 and 390 px**. Coverage includes all primary pages, one/multiple reviews, selected detail, source PDF, correction form, empty, resolved, loading, missing selection and mobile list/detail. Layout assertions check page overflow, queue minimum width, panel order, actual PDF rendering, identifier/badge separation, focus and draft preservation.

Native zoom uses a real Chromium window at **80%, 100%, 125%, 150% and 200%**, verifies both device pixel ratio and changing layout viewport, and checks keyboard access to the selected review's Document tab. Screenshots use Chromium's native window capture without a CSS-sized clip; fixed viewport emulation/full-page clips can produce misleading high-zoom crops. The existing additional CSS-zoom checks are retained.

Screenshots below are genuine captures of synthetic QA workspaces, not mockups. Before uses the exact starting committed frontend against the same isolated source data.

- [Before: compressed review and blank detail area](images/review-ux-before-1920.png)
- [After: automatic selection, correction and actual PDF](images/review-ux-after-1920.png)
- [Overview attention queue](images/review-ux-overview-attention.png) and [actual attention card close-up](images/review-ux-attention-closeup.png)
- [Review at narrow desktop width](images/review-ux-selected-1024.png)
- [Mobile review queue](images/review-ux-mobile-list.png)
- [Empty review state](images/review-ux-empty.png)
- [Resolved records included](images/review-ux-resolved.png)
- [Actual loading state](images/review-ux-loading.png)
- [Native 200% browser zoom](images/review-ux-native-200.png)

## Safe Windows update

Stop API, worker and Vite with Ctrl+C. Preserve root `.env`, PostgreSQL volume, port **5434**, Tesseract configuration, all existing workspaces and Git stashes.

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai
git status --short
git diff -- compose.yaml
git stash list
git pull --ff-only origin main
cd backend
uv sync --frozen
cd ..\frontend
npm ci
npm run build
```

If Git reports local edits, preserve and review those edits before pulling; do not reset/clean or pop old stashes. The explicit compose-only preservation procedure is in [the existing Windows guide](workbench-experience.md#safe-windows-cmd-update). No `.env`, compose port or migration change is part of this release. Do not rerun seed/reset/demo-install commands or remove volumes.

Start the existing PostgreSQL service with `docker compose up -d db` from the repository root. Start API and worker in separate backend CMD windows (`uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`, `uv run python -m app.worker.main`) and Vite in a frontend CMD window (`npm run dev -- --port 5173 --strictPort`). Open your configured frontend origin **on that Windows machine**. This is not a public Codex Cloud preview. Continue using the existing Gmail origin and select the existing workspace.

## Remaining limits

Live Gmail authorization/delivery, live Gemini, Auth0, S3, Render, Firefox/Safari and Windows screen-reader testing were not performed. Provider-mocked Gmail tests do not establish live provider behavior. Synthetic QA does not establish real-world extraction generalization. Vendor/PO pagination limits rendered rows using the existing complete-catalogue response; it is not a new server pagination or scale claim. Dense tables scroll horizontally within named, focusable regions on narrow screens. Existing PDF.js bundle-size and Docker `AUTH_MODE` heuristic warnings remain informational; no secrets are included or thresholds raised. No deployment was performed.

## Changed files

```text
README.md
backend/app/review/api.py
backend/tests/application/test_gmail.py
backend/tests/application/test_review_search.py
backend/tests/browser_review_fixture.py
docs/images/review-ux-after-1920.png
docs/images/review-ux-attention-closeup.png
docs/images/review-ux-before-1920.png
docs/images/review-ux-empty.png
docs/images/review-ux-loading.png
docs/images/review-ux-mobile-list.png
docs/images/review-ux-native-200.png
docs/images/review-ux-overview-attention.png
docs/images/review-ux-resolved.png
docs/images/review-ux-selected-1024.png
docs/review-ux-verification.md
frontend/e2e/native-zoom.ts
frontend/e2e/review-ux.spec.ts
frontend/e2e/workbench-zoom.spec.ts
frontend/e2e/workbench.spec.ts
frontend/e2e/zz-asterfield.spec.ts
frontend/src/DocumentViewer.tsx
frontend/src/InvoiceIdentity.test.tsx
frontend/src/InvoiceIdentity.tsx
frontend/src/InvoiceWorkflow.tsx
frontend/src/OverviewInsights.tsx
frontend/src/Reviews.test.tsx
frontend/src/RunDetails.tsx
frontend/src/Workbench.tsx
frontend/src/icons.tsx
frontend/src/main.tsx
frontend/src/pages/Audit.tsx
frontend/src/pages/Dashboard.tsx
frontend/src/pages/EmailIntake.tsx
frontend/src/pages/PurchaseOrders.tsx
frontend/src/pages/Reviews.tsx
frontend/src/pages/Vendors.tsx
frontend/src/pages/WorkspaceSettings.tsx
frontend/src/review-ux.css
frontend/src/ui.tsx
```
