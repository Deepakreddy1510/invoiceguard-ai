# Phase 1 verification

Executed on 2026-11-01 in the current cloud workspace. No deployment or commit was performed. GitHub Actions configuration was added but has not been executed on GitHub.

## Implemented

- Python 3.12 backend with FastAPI, SQLAlchemy, psycopg, Alembic and locked uv dependencies.
- React/TypeScript/Vite frontend with locked npm dependencies and real procurement API integration.
- Local PostgreSQL 17 with persistent Compose volume, loopback binding and health check.
- Workspace, vendor, purchase order and PO item schema; reviewed explicit initial migration, not runtime create_all.
- Repeatable seed: one workspace, three vendors, four POs/items; tax-inclusive gross values verified using Decimal.
- Foundation-only UI with loading/error/retry states and honest scope labels. No processing stages or financial outcomes are invented.
- Local-only startup guard, workspace-scoped read queries and composite vendor/PO workspace foreign key. These do not replace planned hosted authentication.

## Commands executed and outcomes

Run from repository root unless stated otherwise.

| Command | Directory | Observed outcome |
|---|---|---|
| `docker compose up -d --wait db` | root | PostgreSQL healthy |
| `uv sync` | backend | Dependencies installed; uv.lock generated |
| `npm install` | frontend | Dependencies installed; package-lock.json generated |
| `uv run alembic revision --autogenerate -m initial --rev-id 0001` | backend | Initial migration generated and reviewed |
| `uv run alembic upgrade head` | backend | Migration applied to demo database |
| `uv run python -m app.seed` (twice) | backend | Repeatable seed completed |
| `docker compose exec -T db createdb -U invoiceguard invoiceguard_test` | root | Isolated test database created |
| `uv run pytest -q` | backend | **14 passed** |
| `uv run ruff check app tests migrations` | backend | Passed after fixing lint findings |
| `uv run ruff format --check app tests migrations` | backend | Passed |
| `uv run alembic check` | backend | No new upgrade operations detected |
| `DATABASE_URL=postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/invoiceguard_test uv run alembic downgrade base` | backend | Test schema downgraded successfully |
| Same test DATABASE_URL with `uv run alembic upgrade head` | backend | Test schema rebuilt successfully |
| `uv run pytest -q` after roundtrip | backend | **14 passed** again |
| `npm run build` | frontend | TypeScript check and production Vite build passed |
| `npm test` | frontend | **2 passed** |
| `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` | backend | Application startup complete |
| `npm run dev -- --port 5173 --strictPort` | frontend | Development server ready |
| `curl --fail --silent http://127.0.0.1:8000/api/v1/health/ready` | any | ready / database connected |
| `curl --fail --silent http://127.0.0.1:5173/api/v1/purchase-orders` | any | Four real seeded PO records through frontend proxy |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e` | frontend | **1 passed** using installed Chromium |
| `git diff --check` | root | Passed |

Test counts total 17 distinct tests, not cumulative reruns. Backend parameterized cases count as individual tests. Browser test exercises the real UI/API/PostgreSQL path. Component tests use mocked API responses to test loading/error behavior; they are not substitutes for the browser test.

## Failures investigated and remaining limitations

- Initial sandbox network and Docker access were unavailable. Authorized elevated execution reached the managed Docker socket/package registries and completed installation/tests without disabling TLS.
- Initial lint detected import/format and FastAPI default-argument findings; corrected, final lint and formatting pass.
- Default Playwright browser download failed with HTTP 403 `Domain forbidden` for cdn.playwright.dev. Used the already installed `/usr/bin/chromium`; the actual browser test passed. Fresh environments without Chromium need that download destination allowed or a supported system browser installed. No network allowlist was changed.
- Backend test collection emits a Starlette TestClient/httpx deprecation warning. Tests pass; future dependency maintenance should adopt the supported replacement once verified. No warning suppression was added.
- Local UI/API/PostgreSQL are running at handoff; live processes may not survive workspace restoration. Use README startup commands.
- Hosted authentication, uploads, PDF/OCR/Gemini extraction, invoice decisions, run events, financial commitments and extraction evaluation are **not implemented in Phase 1**. The architecture document specifies their required semantics. No measured extraction accuracy is claimed.

## Exact Phase 2 handoff

1. Add the minimal document/submission, canonical invoice/revision, run/stage/event, job, decision and commitment migration, keeping identities separate.
2. Create development PDFs in at least two layouts; independently label held-out fields/evidence before tuning prompts. Keep labels out of runtime processing.
3. Implement safe streamed PDF upload, hash/idempotency replay and private local storage adapter; link UI upload to the API.
4. Add page-aware PyMuPDF extraction and Tesseract OCR with bounded resource usage.
5. Implement genuine Gemini structured-output adapter with Pydantic validation, source evidence checks, model/prompt recording, timeout/rate-limit handling and conservative fallback. Confirm required API binding/domain access without logging credentials. A mock does not prove the live adapter works.
6. Add minimal durable worker and persisted stage events; browser polls actual history.
7. Match verified vendor and explicit seeded PO; execute mandatory/vendor/status/currency/arithmetic/evidence controls.
8. Finalize supported happy path under invoice/PO locks with a single reservation and atomic decision/event persistence; exercise replay and competing-reservation tests before claiming balance safety.
9. Display decision, evidence, stage history and saved result in React; rerun after browser/API restart to verify persistence.
10. Execute real digital/scanned uploads, live Gemini when configured, outage fallback, missing-field review, duplicate replay and browser tests. Report executed outcomes and blockers, then stop for Phase 2 review.
