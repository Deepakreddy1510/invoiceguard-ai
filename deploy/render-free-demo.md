# Render Free-only temporary assignment demo

**Preparation only: no Render deployment or AWS resource creation was performed.** Use `deploy/render-free-demo.yaml`, not the existing paid `deploy/render.yaml`. The paid Blueprint and root Dockerfile are unchanged.

This candidate uses exactly **one Free Docker web service and one Free PostgreSQL database**, plus the already-existing private S3 storage and existing Supabase configuration. There is no separate Render worker, persistent disk, paid plan or pre-deploy command. Automatic deployments are disabled. Creating the Blueprint in Render is still a real provisioning/deployment action performed by the owner, not by committing these files.

## Can this be completely free and reliable?

**No guarantee of full-application reliability or zero total cost can be made.** This is a temporary, small, synthetic-document demo option, not an always-on production replacement.

- Free web services sleep when idle (commonly after 15 minutes). API requests can wake the service, with cold-start delay; queued jobs and Gmail polling cannot wake it themselves. Monthly free-hour/build/bandwidth quotas can suspend availability.
- Free PostgreSQL has historically had a 30-day lifetime and 1 GB storage limit, and is not a durable long-term ledger/backup service. Use the **actual expiry and limits shown in your account** as the deadline. Never promise immutable history will survive expiration/deletion without a separately verified backup/restore plan. Expiration also loses PO capacity state even though original PDFs remain in S3; PDF storage alone cannot reconstruct the ledger safely.
- Free web memory has commonly been 512 MB with limited shared CPU. One API, a worker and Tesseract share that budget. Existing PDF limits allow 20 pages and up to 18 million rendered pixels per page; the PDF subprocess's 1.5 GB address-space cap is **not** a guarantee it fits a 512 MB container. Large/photo-heavy PDFs or concurrent uploads can OOM/restart the whole service. The full supported workload cannot be certified reliable within Free memory here. Do not lower evidence/financial checks to hide this limitation. Use small synthetic PDFs, one upload at a time, and measure the real instance before the assignment.
- S3 requests/storage/transfer and Gemini calls use their existing providers' quotas/pricing; choosing Free Render plans does not make those services universally free. This work creates no bucket, IAM identity, AWS service or real provider call. Leave Gemini unconfigured if its use is not already authorized; Standard extraction remains available. Never replace existing secrets to change this.
- Account eligibility, a Free database slot and no-card provisioning must be confirmed in Render. If Render asks for a card or shows a paid resource, **stop**; do not choose Starter, Basic, a converting trial or a paid workspace to proceed.

Official references for the owner: [Free services](https://render.com/docs/free), [Blueprint specification](https://render.com/docs/blueprint-spec), [Docker services](https://render.com/docs/docker), [PostgreSQL](https://render.com/docs/postgresql), [pricing](https://render.com/pricing). The direct documentation fetch returned HTTP 403 from this environment; live plan eligibility/limits and account-side Blueprint validation are **not verified**. Local YAML parsing and process tests do not substitute for those checks.

## Supervision and restart behavior

The Blueprint overrides only this service's command with `python -m scripts.run_free_demo`. The existing Docker image still contains compiled React, FastAPI, Tesseract and the normal worker. The paid web/worker commands are unchanged.

1. Fail closed unless `APP_ENVIRONMENT=production`, `AUTH_MODE=supabase` and `STORAGE_BACKEND=s3`, using existing runtime checks.
2. Run the existing additive `alembic upgrade head` in a child process at startup, serialized by a PostgreSQL advisory transaction lock across overlapping starts. Free does not require a paid pre-deploy feature. No seed, reset, demo installer or customer-data migration is invoked.
3. After successful migration, launch exactly one Uvicorn process (`--workers 1`, Render's `$PORT`, host `0.0.0.0`) and exactly one `app.worker.main` process. There is no worker in FastAPI lifespan, no reload mode and no request-triggered second worker.
4. If either service exits unexpectedly, including an exit code of zero, stop its sibling and exit nonzero. Render controls container restart/backoff. The supervisor does not leave a healthy web process hiding an exited worker. A live worker with a temporary dependency error retains its existing bounded retry behavior; readiness still checks the database.
5. SIGTERM/SIGINT shuts down whole process groups, including PDF/OCR descendants, allowing up to 20 seconds before forced cleanup. Uvicorn gets a 15-second graceful timeout. Configure at least a 30-second termination allowance if your provider exposes one. Crash/sleep interruptions retain durable jobs in PostgreSQL.
6. Existing database row/workspace locks, lease tokens, attempt limits, uniqueness constraints and stale-worker fencing remain authoritative. Rolling overlap or a crash may repeat technical work after the 180-second lease expires; this is not a promise of exactly-once execution. Stale workers cannot finalize financial outcomes, and duplicates cannot consume PO capacity twice. Repeated interruption can correctly fail a run and require an explicit retry.

Do not add a second worker service, launch extra worker commands in a shell, enable Uvicorn reload/multiple workers, or point both paid and Free environments at the same production workload. There are no keep-alive tricks to evade Render's sleep/free quotas.

## Required configuration — reuse the existing group

The Blueprint references **`invoiceguard-runtime`**. Keep all secret values in that existing Render environment group or per-service secret settings, never in GitHub or chat. Do not change a shared group's values merely to point this demo at a new URL: group edits can affect existing paid services. Set demo-specific origins as **per-service overrides**.

| Variable | Source / required value |
| --- | --- |
| `DATABASE_URL` | Automatically injected from `invoiceguard-free-demo-db`'s internal connection string. This service-specific setting overrides any shared-group database URL. Do not paste a production/local database URL here. |
| `APP_ENVIRONMENT` | Blueprint forces `production`. |
| `AUTH_MODE` | Blueprint forces `supabase`; never use public local/demo authentication. |
| `STORAGE_BACKEND` | Blueprint forces `s3`; no local-storage fallback. |
| `STORAGE_DIR` | Blueprint sets `/tmp/invoiceguard-staging`, for temporary upload/processing files only. Originals are uploaded to S3 before ingestion commits; reads use the existing bounded temporary S3 download. |
| `SUPABASE_URL` | Existing HTTPS Supabase project origin from the group. |
| `SUPABASE_PUBLISHABLE_KEY` | Existing public `sb_publishable_...` key. Do not substitute a service-role secret. |
| `S3_BUCKET`, `AWS_DEFAULT_REGION` | Existing private bucket and its actual region. Do not create a bucket. |
| `S3_PREFIX` | Retain the existing authorized prefix, if configured. Do not change existing object keys or copy customer objects. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN` | Existing restricted runtime credentials from private settings, or the existing supported runtime identity. Never create new IAM resources for this demo. |
| `S3_ENDPOINT_URL` | Omit for AWS S3; retain only if already intentionally using a compatible private service. |
| `FRONTEND_ORIGIN` | Per-service override to the actual demo HTTPS origin when known. |
| `PORT` | Provided by Render; do not hardcode a conflicting port. |
| `OMP_THREAD_LIMIT` | Blueprint sets `1`; PDF resource/timeout checks remain unchanged. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional existing authorized values. No key means Standard fallback. No live Gemini claim until a verified call succeeds. |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_ENCRYPTION_KEY`, `GMAIL_POLL_SECONDS`, `GMAIL_USE_GEMINI` | Optional existing configuration. Preserve encryption keys; this Blueprint does not enable Gmail AI, change scopes or connect a mailbox. |
| `GMAIL_TRUSTED_ORIGIN`, `GMAIL_REDIRECT_URI` | If Gmail is explicitly tested, per-service demo HTTPS origin and `https://ACTUAL-DEMO-HOST/api/v1/email/oauth/callback`. Add the exact callback in the existing OAuth client; retain existing callbacks for other environments. |

## Exact owner deployment steps

1. Open Render in the intended Free/Hobby workspace. Confirm Free web and Free PostgreSQL eligibility, remaining free quotas and any existing Free database. No card or paid workspace should be selected. This new configuration does not cancel/convert any paid resources a previous attempt may already have provisioned; inspect those separately without changing the paid Blueprint.
2. Confirm `invoiceguard-runtime` already contains the required Supabase and existing private S3 settings. Do not rotate credentials/encryption keys, create S3/IAM resources, or publish environment values. Retain private bucket access controls/encryption. The app needs access to its existing object prefix, not bucket creation.
3. Choose **New → Blueprint**, authorize only `Deepakreddy1510/invoiceguard-ai`, branch `main`. Set the Blueprint path explicitly to **`deploy/render-free-demo.yaml`**. Do not accept the default paid `deploy/render.yaml` path.
4. Review the preview before applying: exactly `invoiceguard-free-demo` (**Free web**) and `invoiceguard-free-demo-db` (**Free PostgreSQL**), both Oregon; no worker resource, disk, paid plan or upgrade. Confirm the existing group is reused. If the preview rejects Free, requires payment information or substitutes a paid plan, stop and report that account/provider blocker. Local preparation cannot override it.
5. Apply only this Free Blueprint if the preview meets those conditions. Startup migrations run before the API/worker. Read logs for migration success and both processes; do not run reset/seed commands. The new Free database is empty and separate from every existing customer/paid database; no existing financial histories or memberships are copied, deleted or reset.
6. Set this web service's `FRONTEND_ORIGIN` to its actual assigned HTTPS origin. In the existing Supabase project add the exact demo Site/confirmation/recovery redirect URL according to [customer access](../docs/customer-access.md), preserving other application's redirect entries. Use verified accounts with normal memberships; new accounts bootstrap their own empty workspace. Never grant membership from browser input or share a service-role key.
7. Manually redeploy after configuration changes if Render requires it. Auto-deploy remains disabled. Share the actual HTTPS URL only after the checks below. Plan the assignment before the database's displayed expiry; record a backup/retention plan before using any history that must survive.

## Verification procedure on the actual Free deployment

Use synthetic data and an authorized test account. No local test here establishes Render deployment success.

1. Check `https://ACTUAL-DEMO-HOST/api/v1/health/ready` returns 200 and `/` serves React, including deep links after refresh. `/api/v1/config` should expose only public configuration. Anonymous dashboard/review/document requests must return 401. Cold starts are expected; do not weaken auth to make readiness easier.
2. Confirm one Uvicorn worker and one invoice worker in logs/process reporting, migrations at head, and a recent worker heartbeat in the authenticated dashboard. Check no repeated sibling-exit/restart loop and inspect Render memory metrics. A 200 health endpoint alone does not prove OCR or S3 access.
3. Sign in with two separate Supabase accounts. Create an empty company, manually create a supplier/PO, then upload one small digital invoice and one small scanned PDF. Verify actual stage events, OCR method, extraction provider/model or fallback reason, original PDF and saved decision. Test a missing reference/review, different-byte duplicate and over-budget invoice; extra capacity must not be consumed. Account B must not access account A's workspaces/PDFs/procurement/Gmail with forged IDs.
4. Confirm original bytes are in the existing private S3 prefix and public object access is denied. Restart the Free service and re-open the original PDF and financial records. A staged local PDF must never be the only copy. Do not create AWS resources to make the check pass.
5. Allow ordinary sleep/cold wake behavior and confirm queued work resumes after startup/lease expiry, retaining attempt history. Re-open the page to wake it; do not use artificial keep-alive polling. An in-progress job can be interrupted and can eventually require explicit retry. If OCR/OOM or cold-start timing makes the assignment unreliable, report the Free-tier blocker; do not claim full support.
6. Gmail polling runs only while this shared web container is awake. Sleep delays inbox discovery, refresh/revocation retries and processing; there is no always-on worker or guaranteed mail-arrival latency. Do not connect a production mailbox already processed by a different database/environment. If authorized, use a separate synthetic test mailbox and verify actual OAuth/read-only intake and wake-up recovery. Live Gmail/Gemini remain unverified until configured and observed; no automatic AI transfer is enabled.
7. Before Free PostgreSQL expires, preserve required data outside the expiring service with a verified private PostgreSQL backup and retained encryption key. Free automatic backups/export features are not assumed. If using `pg_dump` from your computer, use the database's actual external connection privately and temporarily authorize only your IP as required, then revoke that external access. Do not put connection strings/backups in GitHub. **Do not deploy this Free database as the sole long-term copy of an immutable financial ledger.**

## Local targeted verification

**37 targeted tests passed.** The Blueprint also parsed with a real YAML parser as exactly one Free web service and one Free PostgreSQL database, reusing the existing environment group. Backend Ruff lint/format passed; the secret scan found no leaks. Git comparison confirmed `deploy/render.yaml` and `Dockerfile` are unchanged. Tests exercise Free-only topology, failed migration gating, sibling shutdown on web/worker exit (including exit 0), SIGTERM propagation, stop-during-migration, fail-closed runtime settings and a real supervised API/worker startup with database readiness, heartbeat and anonymous 401. Existing private S3 stub tests and financial lease/fencing/transaction regressions are run without real AWS or paid provider calls.

These are local process/application tests, not a live Render deployment, Free memory load certification, real Supabase sign-in or real S3/IAM verification. The existing image/Dockerfile is reused; no claim of a newly built image or account-side Render validation is made without executing those checks.
