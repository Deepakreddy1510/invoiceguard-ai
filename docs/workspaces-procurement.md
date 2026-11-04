# Workspaces, procurement management and extraction modes

The sidebar selector sits below the logo. **Demo Workspace** opens the existing prepared data and history; **My Workspace** is a private, initially empty procurement workspace. Both use the same actual invoice pipeline. The application never resets a database or changes the original seeded vendors, purchase orders, decisions or reservations during migration.

## Upgrade on Windows CMD

Run these commands in **Command Prompt**, substituting the path to your existing checkout. Stop the API and worker first with Ctrl+C in their terminals. Keep your existing ignored `.env` and Docker volume. Do not run a reset command, `docker compose down -v`, or a seed script when upgrading.

```bat
cd /d C:\Users\YOUR_NAME\invoiceguard-ai
git status --short
git pull --ff-only origin main
docker compose up -d --wait db
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run alembic check
cd ..\frontend
npm ci
npm run build
```

If `git status` shows your own changes, preserve them before pulling; do not discard them. `alembic upgrade head` applies additive migration **0007**, preserving all financial rows. Existing configuration and membership invitations continue to work. No new required environment variables or seed commands are needed for an existing installation.

Open three CMD terminals, with the same repository path:

```bat
cd /d C:\Users\YOUR_NAME\invoiceguard-ai\backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd /d C:\Users\YOUR_NAME\invoiceguard-ai\backend
uv run python -m app.worker.main
```

```bat
cd /d C:\Users\YOUR_NAME\invoiceguard-ai\frontend
npm run dev -- --port 5173 --strictPort
```

Open the Vite address **on that Windows computer**. These commands run the real application locally; a Codex Cloud loopback address is not accessible from your laptop. No deployment or public preview is created by this change. PostgreSQL, both Python processes and Vite must stay running. Existing Python 3.12, uv, Node 24, Docker Compose v2 and Tesseract English prerequisites still apply. With a nonstandard Windows Tesseract installation, ensure `tesseract --version` works in the worker terminal.

For a new installation, follow the existing README setup to initialize the first synthetic workspace and authorization. Bootstrapping a signed-in, invited account adds only its empty My Workspace; it does not silently seed or rewrite existing Demo data. An administrator can create the expanded fresh demo through the sidebar. The first authorized local workspace must exist before uploading invoices.

## Workspace access and switching

- Every API, search, original-PDF read, upload and mutation carries the selected `X-Workspace-ID`. The backend checks membership on each request. OIDC tokens remain in the existing Auth0 in-memory SDK; no authentication secrets are added to storage.
- A hosted user must already have a server-provisioned membership to use the application. Bootstrapping creates an ADMIN membership only for that subject's own new My Workspace. It never grants membership to another user's private workspace or upgrades a role in an existing shared workspace. Hosted local authentication remains forbidden.
- Local development uses the existing single trusted local identity and needs no external login. It can access the configured local demo, the expanded synthetic demo, and workspaces owned by that local identity. Local mode is not a multi-user authentication boundary and must never be exposed publicly.
- Workspace selection is remembered per verified subject in session storage, storing only an ID. Switching aborts old requests, rejects late responses, remounts workspace pages/caches and returns to Overview. A permitted Demo is the default; a previous selection in the same tab is retained.
- My Workspace starts with no vendors, POs, invoices or runs. Its workspace-creation audit entry is real administrative history, not invoice processing.

**Create fresh demo** is ADMIN-only and asks for explicit confirmation in the sidebar. It creates a new owned, isolated Demo with 18 vendors, 36 POs, and 16 real queued PDF submissions, including scanned, missing-field, duplicate, partial and overbilling examples. The running worker creates the extraction events, decisions and commitments. The UI does not mark queued examples complete. Existing demo workspaces remain selectable, and their rows remain intact. Repeating the same request ID is idempotent. No synchronous shared reset is offered. Creation may take several seconds; interrupted requests can be retried safely with the same ID.

## Vendor and purchase-order rules

REVIEWER and ADMIN users can manage procurement; VIEWER users can inspect it. All mutations use a PostgreSQL transaction, the existing workspace financial lock, audit entries and version checks to reject stale edits.

Vendor codes are unique within the workspace after normalization; contradictory tax IDs are rejected. Existing synthetic ambiguity records are preserved. A vendor without dependencies can be edited or deleted. A vendor with POs or invoice identity history retains its legal name, code and tax identity; deactivate or suspend it instead. This restriction is deliberately conservative even before a linked PO has been billed. These statuses use the unchanged validation engine.

Create POs using a vendor in the active workspace, currency, status, dates, billing mode and decimal-string amounts. Itemized POs need unique SKUs, positive quantities, nonnegative prices, fractional tax rates between 0 and 1 and authorization equal to rounded net plus tax. Amount-based POs may omit lines and directly specify authorization. All existing supported currencies remain: USD/INR/EUR/GBP (2 places), JPY (0), KWD (3), with per-line HALF_UP net/tax rounding. Browser calculations use BigInt; the backend independently revalidates using Decimal. Quantity/price inputs allow six decimal places, tax rates eight, matching stored precision.

Unused POs can be edited or deleted. Any decision or commitment referencing a PO locks ordinary editing and deletion; retain it and create a new authorization instead. There is no general historical amendment workflow. Cancellation requires a reason and current version; it **does not release** reserved, held or settled capacity. Existing review/rejection workflows still control eligible unsettled releases. Creating a `PARTIALLY_BILLED` status without a real historical invoice is rejected; process actual invoices to establish consumption. Original seeded partial POs are preserved.

## CSV schema and imports

Download actual templates from the Vendors and Purchase Orders pages, select a file, validate its preview, inspect row errors and commit. Invalid files create no records. Commit revalidates every row against current database state under the financial lock, persists all records in one transaction, and records a hashed idempotent receipt. Limits: UTF-8 (optional BOM), 256 KiB, 500 data rows. Only literal values are accepted; formula-leading `=`, `+`, `-`, `@` cells are rejected. Templates contain synthetic examples and use the current calendar year.

Vendor headers:

```csv
legal_name,code,tax_id,status
Example Supplier (Synthetic),MY-V001,SYNTHETIC-MY-TAX-001,APPROVED
```

PO headers:

```csv
number,vendor_code,currency,status,issued_on,valid_until,billing_mode,authorized_gross,sku,description,quantity,unit_price,tax_rate
MY-PO-001,MY-V001,USD,OPEN,2026-01-01,2026-12-31,ITEMIZED,220.00,PAPER-A4,Synthetic paper cartons,10,20,0.10
MY-PO-002,MY-V001,USD,OPEN,2026-01-01,2026-12-31,AMOUNT_BASED,1000.00,,,,,
```

Import vendors first. Repeated PO numbers group line items; repeat identical PO header columns for each item row. For amount-based authorization without items, leave all five item columns empty. Dates above are illustrative; replace them with the dates your invoice requires. No separate item import service or spreadsheet execution is needed. Imported records are immediately usable by the worker.

## Invoice management and extraction comparison

Invoice history supports invoice-number, vendor and PO search plus financial-decision filters. Original PDFs, evidence, rules, retries, review requests, linked POs, commitments and immutable audit history remain accessible. Processing status (QUEUED/RUNNING/SUCCEEDED/FAILED) remains separate from business outcome (VALIDATED/NEEDS_REVIEW/BLOCKED).

All uploads are audited at acceptance, so ordinary hard deletion is unavailable even before processing. The UI explains retention. The DELETE API refuses historical removal, including settled invoices. Use the existing attributed review/rejection workflow when a disposition is needed; deleting a list entry cannot release money.

- **Automatic — Recommended / AUTO**: default behavior. Attempts configured Gemini, otherwise conservative fallback; records the safe fallback reason.
- **Gemini AI / GEMINI**: disabled if no server key. Requires the real configured adapter. Provider failure or unsupported evidence produces a technical FAILED run, with no silent fallback or invented decision. Existing consuming commitments remain held for review when a comparison fails.
- **Rule-based / FALLBACK**: reads PDF/OCR and source evidence normally, then uses the real deterministic parser and financial engine; it never calls Gemini.

Local ADMIN users can compare modes. For hosted ADMIN users, optional **`ALLOW_MANUAL_EXTRACTION_MODES=true`** enables manual selection (default false); REVIEWER/VIEWER and ordinary evaluator access remain Automatic-only. This is a server setting, not a frontend build variable. Keep existing `GEMINI_API_KEY` secret on the API/worker and `GEMINI_MODEL` consistent; the frontend receives only a configured boolean. No new AI provider is added.

Each run records requested mode separately from actual provider, model (only when actually used), fallback reason and sanitized failure information. Re-uploading identical bytes in the same mode replays the existing run. An explicit different mode on a terminal document creates a new linked run/revision of the same canonical invoice. It holds prior unsettled capacity and atomically replaces it only after validation; unique invoice counts and capacity are not duplicated. Changing mode during an active run is rejected. A failed comparison opens the review task; existing retry/correction/rejection controls apply. Settled history requires AP reconciliation, never automatic release.

**Live Gemini remains UNVERIFIED** without a securely configured key. Mocked contract tests verify mode routing and failure bookkeeping, not a successful live provider call. Synthetic tests establish regression behavior, not generalization to all real supplier documents.

## Verification commands

Run backend tests only against a dedicated database whose name ends `_test` (never your demonstration database). The original regressions still run. The browser harness creates and removes its own randomly named database, starts real FastAPI/worker/Vite services and uses actual PDFs. Its temporary artifacts are not deployment assets.

```bat
cd /d C:\Users\YOUR_NAME\invoiceguard-ai\backend
uv run ruff format --check app tests migrations scripts
uv run ruff check app tests migrations scripts
uv run pytest -q
cd ..\frontend
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
cd ..\backend
uv run python -m scripts.browser_regression
```

See [recorded verification](workspace-verification.md) for actual results and limitations. No paid resources, public deployment, live credential changes or evaluation-answer access are involved.
