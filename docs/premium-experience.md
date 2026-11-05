# Premium customer experience

This pass implements the supplied Ramp × Octax principles with an original interface: pale neutral canvas, white cards, navy navigation, coral actions, Inter typography, tabular financial numbers, restrained shadows and accessible semantic status colors. The source websites were unavailable through this environment's network policy; this is not a pixel copy or a claim of inspecting those sites.

## Page-by-page changes

| Area | Customer experience |
| --- | --- |
| Shell | Consistent navigation, a clean selected workspace name, one discreet demo disclosure, responsive menu, nearby workspace actions and Settings. Existing routes remain available. |
| Overview | Actual unique-invoice KPIs, actual outcome distribution, review workload, recent incoming email and business activity. No invented revenue, trends or progress. |
| Invoice processing | Existing real upload/selection/polling workflow, readable extraction modes, provider identity, decision/reason/next action, grouped checks and source evidence. Selecting another run still takes precedence over polling. |
| Invoice details | Six business stages derived from persisted events, original attempt-aware timing, clear processing versus financial outcome, result-at-decision PO comparison and separately refreshed current PO balances. |
| Email Intake | Real connection state and metrics, actionable rows, focused keyboard-contained detail dialog, email/source PDF on the left and decision/reason/next action above extracted fields on the right. Full validation is linked rather than duplicated. |
| Exception review | Guided correction and tax-basis help, source/attestation controls, original version checks and full revalidation. There is no approval bypass. |
| Vendors | Clear status/retention guidance alongside the working search and CRUD flows. |
| Purchase orders | Budget-first hierarchy, current commitments, tax/billing guidance, original CRUD and safe cancellation. CSV import has template/preflight help and readable row previews/errors. |
| Activity | Business events by default, entity/outcome links and useful filters. Routine mailbox polling/heartbeat/checkpoint noise remains available in the retained administrator audit view. |
| Settings | Persistent workspace rename, archive and restore with role checks, confirmation dialogs and conflict/error states. Administrator link to activity history. |

Previously, operational and financial statuses competed with raw technical detail, the email detail view was sprawling, and workspace names/lifecycle could not be managed. The primary path now starts with the recorded financial decision and the next action. Original event/provider payloads remain in one collapsed administrator technical area per page or dialog; they are not deleted or replaced by marketing copy.

## Workspace lifecycle and migration

Migration `0009_workspace_lifecycle` adds `workspaces.archived_at` and optimistic `version`. It also conditionally repairs a missing optional nullable `email_intake_events.evidence` column on earlier prototype schemas. Canonical migration 0008 already defines that column. No historical financial rows or events are rewritten.

Administrators may rename only workspaces they administer. Names retain the original workspace ID, documents, procurement, commitments and Gmail connection. A legacy demo retains its demo identity after renaming. Conflicting versions return 409 rather than silently overwriting another change.

Archive is reversible retention, not deletion. It hides the workspace from normal selection, preserves readable history, denies financial mutations, pauses queued invoice claims and mailbox reads, and leaves commitments intact. At least one accessible active workspace must remain. A live invoice lease, screening lease or mailbox check blocks archive until safe. Claims and archive coordinate with database locks. Restore resumes queued work. Already queued token revocation may finish while archived; it does not read the mailbox. Connections and encrypted credentials are neither copied to another workspace nor erased by archival.

No unrestricted deletion is offered: all application-provisioned financial workspaces have retained audit history. Authentication/JWT and membership contracts remain unchanged; lifecycle authorization is checked against the target workspace.

## Explanation and AI truthfulness

Business reasons summarize actual financial rules and source-backed facts. They are deterministic explanations, not an additional generative narrative service. Missing facts are omitted. Only a real extraction provider result earns the AI-assisted reading label; standard/fallback extraction remains clearly identified. Email classification configuration alone never proves Gemini extracted an invoice. Live Gemini and live Gmail were not exercised in this environment. Existing adapters remain available when credentials are configured.

## Windows CMD upgrade — preserve the existing application

Stop the existing API, worker and Vite with Ctrl+C before upgrading. Use CMD on the Windows computer hosting your current repository:

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai
git status --short
git diff -- compose.yaml
git stash list
git pull --ff-only origin main
```

This release does not change `compose.yaml`. Preserve your local `127.0.0.1:5434:5432` mapping, existing Docker volume, ignored `.env`, real Gemini/Gmail credentials and older stashes. If Git refuses because of local edits, inspect the affected paths first. For an intentional compose-only edit, temporarily protect it using:

```bat
git stash push -m "Preserve Windows PostgreSQL 5434 mapping" -- compose.yaml
git rev-parse stash@{0}
git pull --ff-only origin main
```

Record the printed SHA, then run `git stash apply THE_RECORDED_SHA`, replacing the placeholder. Inspect `git diff -- compose.yaml`, resolve any conflict before continuing, and retain that stash. Do not blindly pop older stashes. Do not paste `.env` or credential output into a public issue.

Confirm your existing `.env` database host port matches **5434**. Do not replace it with the example or change workspace IDs to move data.

```bat
docker compose up -d db
cd backend
uv sync --frozen
uv run alembic upgrade head
cd ..\frontend
npm ci
npm run build
```

Do **not** rerun seeds, regenerate Asterfield, reset a database, remove volumes or use `docker compose down -v` for this upgrade. The migration is the only required database change.

Start each of these in a separate CMD window:

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

Open the Vite address **on that same Windows computer**, keeping the registered Gmail origin `http://localhost:5173`. This is your local repository's real application, not a cloud preview URL. Select Asterfield by its clean company name if it is not already selected. No seeding is required. Verify the existing mailbox connection, a real upload and history after restart. Tesseract must remain on PATH for OCR.

## Before deployment

No deployment or paid plan was activated. Review the new experience locally, then configure approved Render/Auth0/private PostgreSQL/private S3 credentials and authorized evaluator memberships using [deployment instructions](../deploy/README.md). Upgrade schema before restarting the API and worker together. Real OAuth callbacks, live mailbox intake, live Gemini, hosted authentication and persistent storage still require provider-backed verification before presenting a hosted demo as verified.
