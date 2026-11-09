# Supabase authentication verification

Date: 9 November 2026. Base: latest main `4cf46d0` (fetched before implementation). No deployment, payments, paid infrastructure, resets of existing data, volume deletion or credential replacement performed.

## Implementation

The browser now uses `@supabase/supabase-js` for email/password signup and login, confirmation resend, PKCE confirmation callbacks, password recovery/update, persisted sessions, automatic refresh and logout. Loading, errors, expiry and recovery guard private UI. Account changes clear workspace state and abort stale requests. The navy/white/coral design and account menu are retained.

FastAPI accepts only signature-verified Supabase ES256/RS256 user JWTs from the configured project's documented JWKS endpoint. It verifies issuer, authenticated audience, expiry, issued-at, UUID subject/session identity and authenticated role; anonymous and service-role tokens are rejected. Frontend role metadata never grants workspace privileges. Existing membership and reviewer/admin checks remain authoritative.

Existing PostgreSQL workspace provisioning is reused: each verified account starts with its own empty My Workspace and can separately create its isolated Asterfield sample. No Supabase invoice database or automatic legacy membership grant is introduced. Existing Gmail encryption, authorization, worker scoping and financial rules remain unchanged.

[Environment checklist, Supabase Email/URL/template/signing-key setup and Windows startup](customer-access.md).

## Verification results

| Check | Result |
| --- | --- |
| Full backend `pytest -q` | 277 passed, including financial, extraction/OCR and Gmail regressions |
| Final auth/JWT/customer isolation suite | 31 passed, including all 23 final JWT checks |
| Frontend Vitest | 62 passed across 12 files |
| TypeScript / ESLint / Prettier / production frontend build | Passed |
| Backend Ruff lint / format | Passed |
| Alembic upgrade on disposable DB and `alembic check` | Passed; no new upgrade operations |
| Real-service Playwright | 22 passed (9.0 minutes), including provider-mocked SDK flows, real financial processing and Gmail handoff |
| Gitleaks 8.24.3 on publishable source snapshot | Passed; no leaks |
| Docker production image | Canceled near environment disk capacity; see below |

The full backend run included the first 19 JWT cases; four additional JWT edge/key-selection cases were added afterward and all 23 passed in the final 31-test authentication suite. No financial tests were removed or weakened. Existing dependency warnings: FastAPI's httpx test client deprecation, PDF.js Node warning and the production PDF viewer bundle size advisory.

Live Supabase project URL/publishable key and real Gmail consent credentials were unavailable. No live registration or email delivery verification is claimed.

Docker production build was attempted with the managed CA bundle and TLS verification. It reached dependency installation; the 7.9 GB environment approached disk exhaustion (107 MB free), so the build was canceled and only temporary builder cache reclaimed. No PostgreSQL volume was deleted. Production image completion remains a CI verification requirement.

## Authentication and isolation coverage

- Real generated RSA/EC signatures, forged signatures, malformed tokens, wrong issuer/audience, expired or missing claims, anonymous/service roles, invalid UUID identities, shared-secret rejection, documented JWKS path and unknown signing key rejection.
- Two independent UUID-shaped Supabase identities: idempotent bootstrap, distinct private workspaces, forged workspace headers, private vendors/POs, independent Asterfield samples and no copied Gmail credentials.
- Existing cross-workspace document, run, review, audit and Gmail access checks; viewer write/connection denial; source/evidence privacy; archival and immutable history preservation.
- SDK UI tests: signup, login, confirmation guidance/resend, reset email, password update, restored sessions, refresh events, account changes, expiry and confirmed logout.
- Real-service browser regressions use Vite, FastAPI, disposable PostgreSQL and the actual worker. Supabase and Google provider responses are controlled; those tests do not prove live provider access.

## Screenshots

[Login](images/supabase-login.png) · [Signup](images/supabase-registration.png). Captured from the actual application with public test configuration, without real account data.

## Remaining live checks

Configure the real public Supabase URL and publishable key in the existing root `.env` and hosted settings when applicable. Enable Email confirmation and asymmetric signing keys, then verify real signup, confirmation delivery/callback, login, reload/refresh, recovery delivery/update, logout and two-account switching. In each account's own workspace, connect its own Gmail mailbox and verify consent, encrypted persistence, worker processing, financial context and cross-account denial. Preserve existing Gmail keys and credentials. Do not deploy as part of this task.

## Publication

Changes are committed and pushed to `main` after the local checks above. The exact commit and observed GitHub Actions status are provided in the task response. CI includes the full backend/frontend/browser suites and production Docker build; its status is independent of local results. No deployment workflow is invoked.

## Changed files

- `.env.example`
- `.github/workflows/ci.yml`
- `Dockerfile`
- `README.md`
- `backend/app/auth.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/scripts/verify_hosted_preview.py`
- `backend/tests/application/test_customer_auth.py`
- `backend/tests/application/test_gmail.py`
- `backend/tests/application/test_product.py`
- `backend/tests/application/test_security.py`
- `backend/tests/application/test_supabase_tokens.py`
- `backend/tests/application/test_workspace_lifecycle.py`
- `deploy/README.md`
- `docs/customer-access.md`
- `docs/images/supabase-login.png`
- `docs/images/supabase-registration.png`
- `docs/supabase-verification.md`
- `frontend/e2e/customer-access.spec.ts`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/auth.css`
- `frontend/src/auth.test.tsx`
- `frontend/src/auth.tsx`
- `frontend/vite.config.ts`
