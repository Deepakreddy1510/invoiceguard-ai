# InvoiceGuard frontend — editorial UI pass

This change is confined to `frontend/`. FastAPI, authentication contracts, PostgreSQL models/migrations, worker processing, procurement data and financial rules are unchanged. No public deployment or paid service was activated.

## Design and interaction

The application uses warm ivory surfaces, terracotta accents, Source Serif 4 headings/statistics, Inter interface typography, accessible status variants, restrained shadows and consistent controls. Google Fonts stylesheets are linked; licensed local variable-font fallbacks are bundled so typography still works without external font access. The sidebar collapses below 900 px, with keyboard-operated navigation; tables scroll inside their containers on narrow screens.

Process Invoice includes a keyboard-accessible dropzone, PDF/size validation, selected-file removal/preview, automatic receipt-based run selection, manual selection preservation (including upload races), history filters, retry/revision/duplicate indicators and completion notifications. Actual technical status and financial outcome are displayed separately. Run details poll every second until SUCCEEDED/FAILED; history continues polling for new submissions. Polling is sequential and aborted on navigation. No local timer advances a stage or invents output.

The timeline groups the existing ingestion, text extraction, OCR, field extraction, validation and decision stages. Pending means no corresponding event has been observed, not that execution was performed. Operational worker/retry/review records remain available in the complete persisted event log. Review-disposition runs show their actual disposition stage instead of a fabricated extraction pipeline. Original PDFs, evidence pages/quotes, verified/unverified fields, line items, matched PO links, backend calculations, rule outcomes and explanations remain available. Successful rule lists can be expanded; exceptions are highlighted. The final decision includes only backend explanations.

The overview refreshes automatically and provides clickable outcome statistics, counted filter chips, a real outcome-distribution bar, worker/technical-failure/run metrics and linked activity including actual amounts/durations. Reviews retain comments, field/item corrections, source confirmation, optimistic revision checks, revalidation, rejection/release and previous decisions. Purchase orders show actual capacity, utilization, items and linked commitments; query links select the referenced PO. Audit history humanizes labels, threads by run, filters by stage/actor, supports copying JSON, and retains pagination/run navigation. Loading, empty, error/retry, reduced-motion and focus states share the theme.

## Data boundaries and known limits

- There are no API progress percentages, numeric extraction-confidence scores or stage CPU timings. None is invented. The elapsed clock measures wall time from persisted run creation through `finished_at`, including queue time. A stage interval is shown only when that same attempt has matching recorded RUNNING and terminal events. Ingestion, OCR and decision often have no start event, so their durations are omitted. Fast stages can complete between polls; their persisted events remain visible without a simulated replay.
- The run-summary API omits amounts and duplicate-rule details. The UI obtains them from real run-detail requests with a bounded four-request batch/cache. Missing optional values remain absent/dashes; there is no assumed invoice currency or amount. Display-only PO utilization is calculated from provided decimal balances and does not change financial rules.
- Run-history chips filter the current 20-run page; audit stage/actor filters apply to the current 50-event page, explicitly labelled. Dashboard search/outcome filters use the existing backend filtering endpoint. Pagination remains available.
- Source evidence verification has no numeric confidence; review flags use the backend `verified` value. Financial-policy flags can remain unresolved after a source correction because full backend controls still run.
- The optional sample-PDF shortcut was not added. Existing repository samples can be chosen with Browse and use exactly the same real upload pipeline; synthetic samples must match the chosen workspace's procurement catalogue.
- Clipboard access can be denied by browser policy; a manual-copy message is displayed. Authentication-provider login and live Gemini are outside this frontend pass. The cloud has no public preview capability; internal integration checks are not a hosted-website claim.

## Frontend checks

From this directory:

```sh
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

For real-service browser tests, install Chromium with `npx playwright install chromium`, then use the existing repository harness from `backend`:

```sh
uv run python -m scripts.browser_regression
```

It starts the unchanged API, real worker, Vite and an owned disposable PostgreSQL database, and cleans them up. Existing demo balances/history are not reset. Python/Tesseract/PostgreSQL prerequisites and database-creation permissions are described in the root README. `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can select a system Chromium. Browser fixture generation supports the Windows `.venv/Scripts/python.exe` path.

The expanded tests cover automatic/manual run selection, upload races, file validation, truthful stage/decision separation, polling stop conditions and matched-attempt timing. Browser tests retain all previous financial workflows and add a freshly generated scanned invoice with live API snapshots, automatic Overview/Audit updates, keyboard/mobile behavior and axe WCAG A/AA checks across the primary screens. Automated accessibility checks are not a substitute for a full assistive-technology audit.

## Pull into an existing Windows checkout

In PowerShell, replace the example folder with your actual repository directory:

```powershell
Set-Location C:\path\to\invoiceguard-ai
git status
```

If it shows your own uncommitted work, commit it or preserve it with `git stash push -u -m "Before InvoiceGuard UI refresh"` before switching branches. Keep your ignored `.env` and local database; do not run a reset, `git clean`, or discard changes. Then:

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
Set-Location frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

If `main` does not exist locally, use `git switch --track origin/main` instead. If Git reports divergence, stop and merge/rebase your local work deliberately; do not force-reset it. If you stashed changes, use `git stash pop` only when ready to reconcile them.

Start your existing local PostgreSQL, FastAPI and worker using the root README, with the same local settings as before. Vite proxies `/api` to port 8000 by default; `API_PROXY_TARGET` is a frontend development override when necessary. Open the Vite address printed in **your Windows terminal** using your Windows browser. Pulling the frontend does not start backend services or change their credentials. No Codex-only loopback URL or screenshot is required.

## Verified results for this pass

Formatting, ESLint with zero warnings, TypeScript validation and the production build passed. Component tests: **11 passed, zero failed**. Real-service Chromium tests: **10 passed, zero failed** in the final 58.1-second run, using the unchanged FastAPI/worker and a disposable PostgreSQL database. The new six-page scanned invoice was observed queued/running before its real persisted VALIDATED decision; the actual OCR events, source evidence and financial checks were displayed. Already-open Overview and Audit pages updated without refresh, and manual history selection stayed selected. The existing demo database was not reset.

The browser suite also detected no axe WCAG A/AA violations on the five primary screens, checked mobile navigation and document-width overflow at 1024 px/390 px, and retained the previous duplicate, missing-field, overbilling/partial-invoice, correction, OCR, corrupt-file and replay checks. No live Gemini or hosted Auth0 verification is claimed. Internal desktop/mobile visual inspections were completed; screenshots are test artifacts, not a replacement for the application.

Initial checks found and fixed logo contrast, a scanned-PDF test-buffer limit and old upload-test synchronization assumptions. Upload assertions now wait for the actual accepted run ID rather than whichever old record is already visible. A multi-page scan exercises genuine live OCR, avoiding an assumption that a very short stage must be caught between polls.

## Every changed file

- `frontend/.prettierignore`
- `frontend/README.md`
- `frontend/e2e/complete.spec.ts`
- `frontend/e2e/foundation.spec.ts`
- `frontend/e2e/redesign.spec.ts`
- `frontend/e2e/workflow.spec.ts`
- `frontend/eslint.config.mjs`
- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/playwright.config.ts`
- `frontend/src/App.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/InvoiceWorkflow.test.tsx`
- `frontend/src/InvoiceWorkflow.tsx`
- `frontend/src/RunDetails.test.tsx`
- `frontend/src/RunDetails.tsx`
- `frontend/src/api.ts`
- `frontend/src/auth.tsx`
- `frontend/src/client.ts`
- `frontend/src/icons.tsx`
- `frontend/src/main.tsx`
- `frontend/src/models.ts`
- `frontend/src/pages/Audit.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/PurchaseOrders.tsx`
- `frontend/src/pages/Reviews.tsx`
- `frontend/src/run-data.ts`
- `frontend/src/styles.css`
- `frontend/src/test-setup.ts`
- `frontend/src/ui.tsx`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
