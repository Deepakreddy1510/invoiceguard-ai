# Safe Windows local upgrade for the customer PS-1 changes

These commands are for **Windows Command Prompt (CMD)** on the computer holding your existing checkout/database. Replace `C:\path\to\invoiceguard-ai` with that checkout path. Existing prerequisites: Python 3.12, uv, Node 24, Docker Compose/PostgreSQL and Tesseract English on the worker PATH. This is a local upgrade, not a deployment. Native Windows execution has not been verified from this Linux test environment.

## 1. Preserve the existing installation

Let in-progress processing finish, then stop API, worker and Vite with Ctrl+C in their existing terminals. Do not stop/delete the PostgreSQL volume. Keep the existing `.env`, `DATABASE_URL`, storage directory and `GMAIL_ENCRYPTION_KEY`; changing the encryption key makes saved mailbox tokens unreadable. Do not copy `.env.example` over `.env`, run reset/seed/demo installers, use `git reset --hard`, or run `docker compose down -v`.

```cmd
cd /d C:\path\to\invoiceguard-ai
git status --short
git fetch origin
git pull --ff-only origin main
```

If Git reports local changes or cannot fast-forward, stop and preserve/reconcile those changes before upgrading; do not discard them. `git pull` does not update your running services until you restart them.

For the repository's **default local Compose database** (`invoiceguard`, user `invoiceguard`), a backup can be made outside the repository before migration:

```cmd
cd /d C:\path\to\invoiceguard-ai
if not exist ..\invoiceguard-backups mkdir ..\invoiceguard-backups
docker compose up -d --wait db
set "PS1_BACKUP_FILE=..\invoiceguard-backups\before-ps1-%RANDOM%-%RANDOM%.dump"
docker compose exec -T db pg_dump -U invoiceguard -d invoiceguard -Fc > "%PS1_BACKUP_FILE%"
if errorlevel 1 echo BACKUP FAILED - stop before migration
```

Check that the dump succeeded and the output file named by `%PS1_BACKUP_FILE%` is nonempty. Keep each backup; do not overwrite an earlier dump. Treat backups as sensitive: they contain customer history and encrypted mailbox credentials. Preserve the original environment/encryption key securely alongside your normal backup process without committing secrets. If your `DATABASE_URL` points to a different local database or external PostgreSQL, use that installation's established backup procedure and actual database/user; do not blindly back up the Compose default instead.

## 2. Update dependencies and apply the additive migration

In the existing checkout, with the original environment still intact:

```cmd
cd /d C:\path\to\invoiceguard-ai\backend
uv sync --frozen
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

The migration head for this change is `0011`. It adds nullable `invoice_documents.archived_at`; existing documents start unarchived. It does not recalculate financial decisions, release commitments, reinstall samples or alter Gmail credentials. Stop on any migration error; retain the backup and resolve the error before starting services. Do not downgrade to work around it: a downgrade removes the organizational archive flag.

```cmd
cd /d C:\path\to\invoiceguard-ai\frontend
npm ci
npm run typecheck
npm run lint
npm run build
```

The existing large PDF viewer chunk warning is not a failed build. Any command exiting with an error must be resolved before proceeding. Do not point automated test suites at your existing application database; their fixtures require separate disposable `_test`/`_e2e` databases.

## 3. Restart the same local services

API terminal:

```cmd
cd /d C:\path\to\invoiceguard-ai\backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Worker terminal:

```cmd
cd /d C:\path\to\invoiceguard-ai\backend
tesseract --version
uv run python -m app.worker.main
```

Frontend terminal:

```cmd
cd /d C:\path\to\invoiceguard-ai\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://localhost:5173` in your Windows browser, retaining the application's existing allowed origin and registered Gmail OAuth redirect configuration. Do not change OAuth settings or secrets merely to apply this UI upgrade. Refresh the page after services restart. The readiness endpoint is `http://127.0.0.1:8000/api/v1/health/ready`.

## 4. Verify without changing customer history

1. Sign in and confirm all existing workspaces are still available. Collapse navigation and find workspace switching, Create Workspace, Workspace Settings and the account menu.
2. Open an existing invoice and confirm its original PDF, stages, decision and PO balances remain available. Reading method and extraction provider are separate.
3. If desired, explicitly archive an invoice from the queue, view it under Archived invoices, and restore it. Its original PDF and financial capacity must remain unchanged.
4. If a used sample refuses initialization, select **Create Fresh Sample Workspace**, enter a name and confirm. Keep the original workspace; do not delete/archive its invoices to bypass the check. The worker processes the 21 PDFs in the new workspace. Incomplete progress/errors remain visible.
5. Open Vendors/Purchase Orders and check the manual forms and secondary CSV templates. JPG/PNG, XLSX and assisted supplier/PO PDF intake are not supported by this release.
6. Keep Gmail AI disabled unless your existing authorized configuration and provider/data-policy safeguards explicitly permit its use. No setting is automatically enabled by this upgrade. Live provider smoke steps remain in [the Gmail guide](gmail-intake.md).
