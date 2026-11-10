# Workspace creation and processing UX verification

## Behavior

- `POST /api/v1/workspaces` accepts a UUID `request_id`, a visible 1–160 character `name`, and `workspace_type` (`EMPTY` or `SAMPLE`). Creation requires ADMIN access. Identity comes from verified authentication, never the body. Unknown ownership/role fields are rejected.
- Creation is transactional, with a user/request-scoped UUID and PostgreSQL advisory lock. An immutable creation audit receipt detects changed payloads on replay (409). Duplicate names are allowed; UUIDs identify workspaces. Replays after rename retain the current name and do not restart sample processing.
- Empty workspaces use CUSTOM classification and contain no vendors, purchase orders, documents, commitments or Gmail connections. Dashboard onboarding links to procurement setup.
- Sample workspaces use DEMO classification, the existing fictional 18-vendor/36-PO catalogue, and the existing ordered worker initialization of 21 original PDFs. Owner, ADMIN membership and server-created sample provenance gate initialization/resume. Gmail credentials and tenant data are never copied.
- Every authorized active workspace remains selectable, including legacy records. Rename/archive/restore continue through the existing versioned endpoints. Renaming a sample preserves its fictional classification.
- Stage summaries use persisted events from the current attempt (ingestion retains attempt 0). Failed and skipped outcomes remain literal. Unfinished starts on terminal/retry-wait runs appear Incomplete rather than Completed or animated Processing. The expandable immutable timeline preserves every event ID, timestamp, attempt and detail; RUNNING is labeled Historical start. Technical completion remains independent of financial outcome.
- Completed sample setup becomes a compact success acknowledgement. Dismissal is stored per workspace in optional browser storage and retains the sample label and recorded-stage link. Errors and incomplete progress remain visible. Nothing automatically restarts processing.
- Shared focus styles remove competing parent shadows and inner outlines on composite search controls. Normal fields retain one navy outline, sidebar fields use coral against navy, and the light creation form uses navy. Forced-color mode uses system Highlight. Invalid borders and disabled states remain distinct.

## Evidence

Screenshots under `images/workspace-ux/` compare main commit `2088c24` against this change using the same actual, completed blocked sample and workspace:

| Change | Before | After |
| --- | --- | --- |
| Search focus | [Before](images/workspace-ux/before-focus.png) | [After](images/workspace-ux/after-focus.png) |
| Completed blocked activity | [Before](images/workspace-ux/before-activity.png) | [After](images/workspace-ux/after-activity.png) |
| Completed sample acknowledgement | [Before](images/workspace-ux/before-sample.png) | [After](images/workspace-ux/after-sample.png) |

Computed browser styles confirmed the previous 3px blue inner outline plus coral parent shadow; the replacement has no inner outline/shadow and one 2px navy parent outline.

`frontend/src/fixtures/completed-sample-events.json` contains actual persisted events captured from the normal worker's completed BLOCKED sample run. Unit regressions cover this sample, skipped OCR, failure, unfinished stages and multiple attempts. Browser coverage creates Nandi Pipes, creates a separate sample, waits for all 21 scenarios, switches back, checks stage history, dismisses setup, and checks desktop/mobile/forced-color focus. Backend tests use signed test-provider JWTs to check ownership, role enforcement, forged workspace IDs, empty data, sample initialization, immutable receipts and rename/replay behavior.

## Worker investigation and limits

The durable worker already reclaims expired leases, increments attempts and fences stale lease tokens. After three interruptions it records a real FAILED outcome requiring explicit retry. Existing regressions exercise lease reclaim/fencing and sample resume. No worker transition or historical event was rewritten to fix the display issue. The local screenshot database contained 71 SUCCEEDED processing runs and no stale RUNNING run at inspection.

Only isolated local test databases and scratch storage were used. The user's actual local database and hosted service were unavailable, so their live lease state and existing 21 records were not directly inspected. Supabase UI/provider responses and Gmail are controlled in browser tests; backend authentication uses signed JWT verification with a test signing key. Live Supabase registration/Gmail OAuth cannot be validated without configured provider access. No deployment, existing database reset, volume deletion or credential replacement was performed.

## Verification results

- Full backend regression suite: **290 passed** (including Supabase authentication/cross-account checks, creation/name validation/idempotence, sample financial balances/resume, worker lease/fencing, and Gmail workspace isolation).
- Full frontend unit suite: **80 passed** in 13 files.
- Full real-service Chromium browser suite: **25 passed** in one final clean run (7.3 minutes), including native zoom, responsive/focus/accessibility, Gmail isolation, procurement/financial checks and both workspace types.
- Frontend TypeScript, ESLint, Prettier and production build: passed. Build retains the existing PDF viewer chunk-size warning.
- Backend Ruff lint/format and Alembic model/schema consistency: passed; no migration required.
- Gitleaks source scan: no leaks found.

The native sidebar test now waits for browser zoom layout and checks actual navigation visibility before opening the mobile menu. The workbench assertion now checks one row per stage plus the complete immutable timeline instead of expecting historical starts as separate active rows. No assertions were skipped.

Additional browser screenshots: [Create company](images/workspace-ux/create-empty.png), [Empty Nandi Pipes](images/workspace-ux/empty-company.png), [Dismissed completion](images/workspace-ux/sample-complete.png), [Immutable timeline](images/workspace-ux/blocked-stage-summary.png), [Mobile focus](images/workspace-ux/focus-mobile.png).

## Changed files

- Backend: `app/workspaces_api.py`, `app/workspace_service.py`, `app/sample_service.py`, `tests/application/test_workspace_creation.py`.
- Shared frontend/UI: `src/workspaces.tsx`, `src/focus.css`, `src/main.tsx`, `src/App.tsx`, `src/RunDetails.tsx`, `src/pages/Dashboard.tsx`, `src/pages/WorkspaceSettings.tsx`.
- Frontend regressions: `src/workspaces.test.tsx`, `src/RunDetails.test.tsx`, `src/fixtures/completed-sample-events.json`.
- Browser regressions: `e2e/zzzz-workspace-creation.spec.ts`, `e2e/zzz-private-sample.spec.ts`, `e2e/workbench.spec.ts`, `e2e/customer-access.spec.ts`, `e2e/email.spec.ts`, `e2e/product.spec.ts`.
- Evidence: this report and `docs/images/workspace-ux/`.
