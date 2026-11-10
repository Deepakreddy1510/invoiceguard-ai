# Authentication UX, isolated sample history and desktop sidebar

Date: 10 November 2026. Base: latest main `4967483`. No deployment or paid infrastructure. Existing root `.env`, PostgreSQL data/volumes, financial decision rules, Gmail encryption keys and checkpoints are not replaced or reset.

## Changes

- Password visibility uses the existing SVG icon component in Sign In, Create Account and Reset Password. A real `type="button"` control exposes Show/Hide password labels and pressed state, supports keyboard activation, preserves input values/focus/autocomplete, and returns to hidden on mode changes.
- Login maps Supabase error codes (and explicit legacy provider errors) to safe messages. Invalid credentials display “Invalid email or password. Please try again.” Verification guidance appears only for an identified unconfirmed-email condition. Signup success/concealed existing accounts remain neutral and never become a successful login. A synchronous request guard prevents duplicate submissions; changing modes clears stale messages.
- New isolated Asterfield samples retain their 18 suppliers and 36 POs and queue the existing 21 PDFs. Each next PDF is admitted only after its predecessor finishes and its recorded outcome is checked. Source evidence, OCR, stages, decisions, reviews, reservations and audit records come from the existing ingestion and worker pipeline. No financial rules or dashboard counts are fabricated or changed.
- Additive migration `0010` persists workspace-private progress. Session advisory locks and existing ingestion receipt keys make concurrent workers and interrupted commits replay safely. Resume preserves failed runs. Final readiness additionally checks independent PO balance arithmetic. API edits are paused while the sample is incomplete, preserving scenario order.
- Explicit backfill accepts only the account's own pristine empty sample with administrator membership. It refuses existing invoice/commitment history, changed procurement, Gmail connections and consent history. The legacy local Asterfield and My Workspace are preserved. Archival pauses work; restoring permits queued work to continue.
- Desktop navigation uses one outer scroll owner. Reduced navigation/selector spacing fits all seven links at 1700×900, while short screens, mobile and native zoom retain scrolling, keyboard access and visible focus. Completed sample notices do not reduce the Exception Review workbench area.

[Installation, migration, Windows startup and safe backfill instructions](customer-access.md#sample-history-initialization-and-safe-backfill).

## Verification

| Check | Result |
| --- | --- |
| Full backend pytest | 286 passed, including financial, OCR, Gmail and both migration-preservation regressions |
| Final sample + customer-isolation suite | 13 passed, including all 7 sample cases and the final Gmail-history/target-role safeguards |
| Frontend unit tests | 75 passed across 13 files |
| TypeScript, ESLint, Prettier, production frontend build | Passed |
| Ruff lint and formatting | Passed |
| Alembic migration consistency | Passed: no new upgrade operations detected |
| Source secret scan (Gitleaks 8.24.3) | Passed: no leaks |
| Real-service browser regression | All 23 distinct cases passed across the regression run and corrected native-scroll rerun; fresh isolated sample case also rechecked for final screenshots |
| Native sidebar zoom matrix | Passed all 20 combinations, 90/100/125/150/200% × 768/700/600/500px heights |

The full backend collection preceded two additional backfill authorization cases; those final cases passed in the 13-test sample/isolation run. The browser regression run passed 22 cases and timed out in the test that still targeted the obsolete inner navigation scroll area; after targeting the actual outer scroll container, the native matrix passed in a 1.1-minute rerun. The isolated sample screenshot case passed again with the final PDF-render and recorded-activity assertions. No browser failures remain unresolved. Financial assertions remain intact. Migration snapshot tests now sort each table by its declared primary key, including the new `workspace_id` key; the unchanged before/after comparisons still verify financial history preservation. The multi-step financial browser scenarios have 90-second runtime budgets; their assertions are unchanged. The expanded 90–200% viewport matrix targets the actual outer scroll container and passed all 20 combinations, retaining keyboard, focus and overflow assertions.

The API/worker/browser checks use disposable PostgreSQL databases only. Supabase provider responses are controlled for SDK browser tests. Real Supabase email delivery and real Gmail consent were not tested; no live provider credentials are configured in this environment.

## Sample outcomes and counting

The original scenario order produces 21 persisted PDF assessments: 14 validated, 1 needs review and 6 blocked. Partial billing precedes the over-budget invoice; the duplicate follows its original. Scanned/photo PDFs run real OCR. Dashboard totals represent 20 unique invoices: 14 validated, 1 needs review and 5 blocked, plus a separate blocked duplicate assessment. Completion never inserts dashboard totals or synthetic decisions.

## Screenshots

All screenshots are actual application views using fictional accounts and disposable sample records. The visible password is a synthetic test value.

1. [Sign In — hidden password](images/ux-signin-hidden.png)
2. [Sign In — visible password](images/ux-signin-visible.png)
3. [Invalid password](images/ux-signin-invalid.png)
4. [Asterfield outcomes](images/ux-asterfield-dashboard.png)
5. [Recorded processing stages](images/ux-asterfield-recorded-stages.png)
6. [Desktop sidebar at 100%](images/ux-sidebar-desktop-100.png)
7. [Exception Review at 100%](images/ux-exception-review-100.png)

## Publication

Verified changes are committed and pushed to main. Exact commit and observed GitHub Actions status are provided in the task response. No deployment is performed.

## Changed files

- `README.md`
- `backend/app/auth.py`
- `backend/app/models.py`
- `backend/app/sample_service.py`
- `backend/app/worker/main.py`
- `backend/app/workspaces_api.py`
- `backend/migrations/versions/0010_sample_installations.py`
- `backend/tests/application/test_customer_auth.py`
- `backend/tests/application/test_lifecycle_migration.py`
- `backend/tests/application/test_sample_initialization.py`
- `backend/tests/application/test_workspace_migration.py`
- `docs/auth-sample-sidebar-verification.md`
- `docs/customer-access.md`
- `docs/images/ux-asterfield-dashboard.png`
- `docs/images/ux-asterfield-recorded-stages.png`
- `docs/images/ux-exception-review-100.png`
- `docs/images/ux-sidebar-desktop-100.png`
- `docs/images/ux-signin-hidden.png`
- `docs/images/ux-signin-invalid.png`
- `docs/images/ux-signin-visible.png`
- `frontend/e2e/complete.spec.ts`
- `frontend/e2e/customer-access.spec.ts`
- `frontend/e2e/zzz-private-sample.spec.ts`
- `frontend/src/App.tsx`
- `frontend/src/auth.css`
- `frontend/src/auth.test.tsx`
- `frontend/src/auth.tsx`
- `frontend/src/icons.tsx`
- `frontend/src/workbench.css`
- `frontend/src/workspaces.test.tsx`
- `frontend/src/workspaces.tsx`
