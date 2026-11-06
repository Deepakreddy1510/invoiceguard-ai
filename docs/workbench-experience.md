# Invoice workbench and Zamp demonstration

This release changes the application structure, retaining the navy/white/terracotta identity and the existing APIs, financial engine, authentication and workspace lifecycle. No hosted deployment was activated.

## References actually studied

The shadcn blocks site and Octax Dribbble preview could not be fetched through this cloud network. Source references were accessible instead:

| Reference | Actual source studied | Applied pattern |
| --- | --- | --- |
| shadcn/ui dashboard-01 | `apps/v4/registry/new-york-v4/blocks/dashboard-01/page.tsx` | Compact header, inset content and intentional content groups |
| shadcn data table | `.../dashboard-01/components/data-table.tsx` | Tabs, bounded table views, previous/next controls and contextual drawer detail |
| shadcn sidebar | `apps/v4/registry/new-york-v4/ui/sidebar.tsx` | Expanded/collapsed navigation and adaptive layouts |
| shadcn tabs/dialog/drawer | Same `ui/` directory, `tabs.tsx`, `dialog.tsx`, `drawer.tsx` | Accessible selection, focused detail and responsive composition |
| TailAdmin | `src/components/layout/app-layout/index.tsx`, `sidebar/index.tsx` | Layout density and route-specific application shells |
| TailAdmin cards/table | `src/pages/main/dashboard/ecommerce/components/metrics/metric-card.tsx`, `src/pages/main/tables/basic-tables/table-five/index.tsx` | Restrained metrics, table headers, spacing and action placement |

Sources: [shadcn/ui](https://github.com/shadcn-ui/ui), [TailAdmin](https://github.com/TailAdmin/free-react-tailwind-admin-dashboard). TailAdmin source was inspected from commit `df1e9f37e56e0bf83030e8063f5353da2e0ecf18`; its current paths differ from older template releases. Both repositories use MIT licenses, retained in [licenses](licenses/). This implementation uses original React/CSS components informed by those patterns, rather than a template/framework migration. No third-party logo or proprietary asset is shipped. Octax was attempted but is not claimed as visually inspected.

The functional document reader uses **PDF.js 6.5.438**, Apache-2.0. Its original bundled notices are retained, with the license and notice distributed under `frontend/public/licenses/` and the production build's `/licenses/` path.

## Structural changes by page

- **Navigation:** collapsible desktop sidebar, readable compact branding and retained workspace access when switching between desktop and mobile. Existing routes remain available.
- **Invoice Processing:** a server-paginated 20-run queue, a selected record with Overview/Financial checks/Activity/Document tabs, and a side-by-side source PDF at wide widths. Laptop uses two panels; Document opens the reader in its tab. Mobile has explicit list/detail navigation. The queue renders one page, and its detail cache drops records from older pages.
- **Upload:** `+ New invoice` opens a native focused dialog with real file validation, drag/drop, extraction modes and errors. Successful upload selects the new run unless the user chose another record while it was in flight. The dialog may be dismissed while submitting so the user can keep browsing. URLs retain the selected run for refresh.
- **Decision and execution:** processing status is separate from financial outcome. Reasons and next actions reflect stored rules. Six compact stage groups derive from persisted events; OCR appears only when actually recorded. Running/failed steps open automatically, successful steps collapse, and the user may inspect a completed step. Financial output is in its own tab, not repeated throughout the timeline.
- **Original document:** authorized PDF fetches through the existing client, actual page count/navigation, fit-width and zoom controls, expanded viewing, browser opening, loading/error/retry states and cancellation/URL cleanup. No public document URL or third-party viewer service is used. Extracted fields and source quotations remain available.
- **Overview:** smaller headings and metrics, real outcome/review/inbox cards grouped across the available width, six recent rows with a full queue link, and side-by-side recent table/business activity on wide desktops. Counts remain unique-invoice counts; no savings or accuracy percentages were invented.
- **Email Intake:** compact connection status/actions, actual last check, four metrics, existing searchable/filterable paginated inbox, focused source/email/decision dialog and no duplicated full rule report. Connection/privacy/configuration guidance moves to Settings and Manage connection. Provider identity remains factual, including fallback.
- **Exception Review:** compact paginated queue, source PDF beside the correction panel on wide screens, a bounded correction workspace, focused financial checks and collapsed earlier revisions. Mobile retains a clear return to the queue. Attribution, attestation, version conflicts, release restrictions and full revalidation are unchanged.
- **Vendors:** search/status controls, 20-row table pages, focused create/edit dialog, existing identity locks, deletion restrictions and CSV template/preflight flow.
- **Purchase Orders:** 20-row table pages and a focused details dialog with items, balances, commitment history and supported controls. Create/edit uses a focused dialog; stale success feedback clears before a new edit. Original BigInt/Decimal calculations are unchanged.
- **Workspace Settings:** denser active/archived workspace rows with working rename/archive/restore, plus administrator email configuration/privacy information. No destructive deletion is added.
- **Activity/Audit:** consistent compact tables and filters, existing business feed by default and retained administrator technical detail. Background sync records are not deleted or presented as business activity.

Vendor/PO pagination bounds rendered rows using the existing complete-catalogue API responses. Invoice and review queues use existing server-side offset/limit endpoints. No new backend pagination contract or thousands-of-record performance benchmark is claimed.

## Five-minute demonstration

1. Open Overview in the existing Asterfield workspace. Explain the actual outcomes and review workload.
2. Open Invoice processing; select a validated and then a blocked invoice. Compare the recorded decision and next action with its real source PDF. Use Document at laptop widths or Expand PDF for detail.
3. Select `+ New invoice`, upload a fresh supplier PDF, and follow the actual persisted stages. No completion percentage is simulated.
4. Open a review, compare source evidence and supported corrections, then explain that saving runs the financial controls again. There is no approval bypass.
5. Open Email Intake to show actual connection/attachment state, or explain the disconnected setup state honestly. Finish with PO balances and retained activity.

Use original source PDFs and extraction modes consistently when demonstrating exact replay. Financial validation reserves PO capacity; it does not execute payments. Do not regenerate Asterfield for this release.

## Safe Windows CMD update

Use **Node 24** (tested), or Node >=22.13; the new PDF.js package requires it. Keep Python 3.12/uv and Tesseract. Stop the API, worker and Vite with Ctrl+C before pulling.

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai
node --version
git status --short
git diff -- compose.yaml
git stash list
git pull --ff-only origin main
```

This release does not modify `compose.yaml`, `.env` or backend migrations. Preserve your ignored credentials, host **5434** mapping, Docker volume, workspaces, Gmail history, Asterfield and older stashes. If Git refuses due to intentional compose edits, inspect them before changing anything. An explicit compose-only preservation procedure is:

```bat
git stash push -m "Preserve Windows PostgreSQL 5434 mapping" -- compose.yaml
git rev-parse stash@{0}
git pull --ff-only origin main
```

Record the printed stash SHA, then run `git stash apply THE_RECORDED_SHA`, replacing that placeholder. Inspect `git diff -- compose.yaml`; resolve conflicts before starting services and keep the stash retained. Never blindly pop all stashes or use reset/clean to force the update. Do not publish `.env` contents.

```bat
docker compose up -d db
cd backend
uv sync --frozen
uv run alembic upgrade head
cd ..\frontend
npm ci
npm run build
```

There is no new migration in this release. `upgrade head` safely applies any previously pending migration, including 0009 if your Windows checkout has not yet applied it. Confirm the existing `.env` database URL still points to host 5434. **Do not replace `.env`, reset PostgreSQL, remove volumes, rerun seeds or reinstall Asterfield.**

Start each service in a separate CMD window:

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\backend
uv run python -m app.worker.main
```

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\frontend
npm run dev -- --port 5173 --strictPort
```

Open your frontend **on that same Windows computer**, preserving `http://localhost:5173` as the registered Gmail origin. This is not a public Codex Cloud preview URL. Select your existing Asterfield or My Workspace rather than installing another dataset.

## Before deployment

No provider credentials, paid service or public deployment was activated. Live Gmail delivery, live Gemini extraction, Auth0 sign-in/evaluator permissions and private S3 persistence still require tests in the configured environment. Provider-mocked tests do not establish live provider behavior. Follow [hosting instructions](../deploy/README.md) only after provider setup and hosting approval; verify the actual HTTPS upload, blocked/review case and history persistence before recording a hosted demonstration.
