# InvoiceGuard on a VM

## Deployment status and architecture

This is a prepared deployment, **not a publicly verified website**. No VM, paid service, bucket, database or cloud networking was provisioned. The existing Windows Dockerfile/development Compose and both Render Blueprints are unchanged. All existing invoice processing, financial validation, auth and email-intake code is retained; there is one durable worker.

Evaluate hosting in this order:

1. **Oracle Always Free first:** an eligible `VM.Standard.A1.Flex` Linux Arm64 VM, ideally 2 OCPUs/12 GB in the tenancy's home region. Oracle's current published allowance is **1,500 OCPU hours / 9,000 GB-hours per month**, equivalent to 2 OCPUs/12 GB, not the older 4/24 claim. Its documentation lists 200 GB total Always Free boot/block storage across the tenancy (minimum boot volume 47 GB). A 60–80 GB persistent boot disk is sufficient for a small demo plus images/backups, subject to the tenancy's remaining allowance. Capacity, signup/identity/payment verification and account eligibility are not established here. Idle resources may be reclaimed; maintain off-host backups. Do not upgrade or exceed Free eligibility to obtain capacity without approval.
2. **EC2 fallback, only after cost approval:** Linux x86_64 `t3.large` (2 vCPU/8 GiB) with an encrypted 80 GB gp3 volume, in the existing S3 bucket's region. An 8 GB VM provides headroom for image builds, OS, PostgreSQL, API and bounded OCR; merely moving the same complete stack onto 2 GB is not a reliable allocation. Separate containers cap API at 1 GiB, worker at 2 GiB, DB at 768 MiB and proxy at 128 MiB. OCR still has its independent subprocess limits. Do not deploy this configuration onto a 2 GB host without measurement and adjusted resource planning.
3. **Split free hosting not selected:** Vercel cannot host the durable Python/Tesseract worker, sleeping Render cannot guarantee timely jobs/Gmail polling, and no eligible always-on/event worker with measured PDF/OCR resources is established. Moving SQL/storage alone does not resolve the processing constraint.

The selected *deployment design* is one adequately sized VM with independent Docker API/worker containers, persistent PostgreSQL, existing private S3 originals, existing Supabase identities and Caddy HTTPS. Oracle is the preferred provider conditional on eligible capacity; otherwise the same files work on approved EC2. This avoids introducing new queues, caches, database engines or frontend hosts. The VM is a single failure domain, not high availability.

### Costs before any EC2 creation

Illustrative Linux On-Demand us-east-1 pricing, 730 hours/month, USD before tax, discounts or credits:

| Item | Assumption | Approximate monthly cost |
| --- | --- | --- |
| t3.large | $0.0832/hour | $60.74 |
| gp3 | 80 GiB × $0.08/GiB-month; baseline IOPS/throughput | $6.40 |
| Public IPv4 | 1 × $0.005/hour | $3.65 |
| Base total | compute + disk + IPv4 | **$70.79** |

About $2.33/day at that run rate, plus S3 storage/requests/egress, snapshots/backups, domain/DNS, transfer beyond applicable allowances and Gemini usage. Select Standard CPU-credit mode if appropriate to prevent Unlimited surplus-credit charges (sustained OCR may then throttle). Avoid NAT gateways/load balancers for this single public demo VM. Stopped EC2 still incurs retained EBS/snapshot/IP charges. Promotional credits cover only eligible services before expiry; current balance, eligibility and region pricing are unknown. If $100 of credits were fully eligible, $70.79/month would consume them in about 1.41 months before extras; this is not a spending cap. Confirm the account's regional quote and credit terms, then obtain explicit approval before creation. No approval is inferred from possessing credits.

Oracle compute/storage within the confirmed allowance are $0; external S3/Gemini/domain usage is not thereby free. HTTPS certificates from Caddy/ACME have no certificate fee. Sources reviewed during preparation:

- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://www.oracle.com/cloud/free/faq/
- https://aws.amazon.com/ec2/pricing/on-demand/
- https://instances.vantage.sh/aws/ec2/t3.large
- https://aws.amazon.com/ebs/pricing/
- https://aws.amazon.com/vpc/pricing/

### Arm64 support

The Node 24 and Python 3.12 Bookworm base-image manifests include Linux Arm64; PostgreSQL and Caddy publish Arm variants. Locked native dependencies include Arm64 wheels (including PyMuPDF/psycopg/cryptography). Debian supplies Arm64 Tesseract. No x86-only executable is added. The existing Dockerfile builds natively on the target; do not force `linux/amd64` on Oracle. **Only x86_64 was built/executed here; a real Arm64 build plus the smoke tests remain required before claiming compatibility for the selected VM.**

## Owner prerequisites (no automatic provisioning)

Use a supported Linux host with Docker Engine and Compose **v2.30+**, Git, `flock`, OpenSSL, 8+ GB RAM and persistent disk. Install from their official OS/Docker instructions. Enable Docker at boot. Membership in the Docker group grants root-equivalent host access; restrict VM access to operators.

The owner must select an existing eligible VM or approve its creation, configure a domain A record (AAAA only if IPv6 actually works) to its public address, and allow inbound TCP 80/443. Restrict SSH to the operator IP/key or use the provider's secure management access. Do not open 5432/8000 or Docker management ports. OCI security lists/NSGs and host firewall must both allow HTTP/HTTPS. Outbound HTTPS must reach the existing Supabase project/JWKS, existing regional S3 endpoint, Gemini, optional Google OAuth/Gmail, and ACME; DNS/time synchronization must work. No cloud firewall/provisioning changes are made by these files.

Configure Supabase Email signup, confirmation, SMTP delivery and asymmetric signing keys as in [customer-access.md](../../docs/customer-access.md). Set Site URL `https://YOUR-DOMAIN` and exact redirects `https://YOUR-DOMAIN/` and `https://YOUR-DOMAIN/?auth=recovery`. Anonymous sign-in stays disabled. The existing create-account/login UI and verified JWT membership bootstrap are used; no shared administrator or public local-auth session is added.

For `deepakreddy1510@gmail.com`, sign in through that existing verified Supabase account. Workspace access derives from its signed `sub` and server-side membership, never an email string match. Confirm the user UUID in the correct Supabase project before any explicit membership grant.

Use existing bucket `invoiceguard-ai-demo-2026-unique123`; confirm its actual region privately. Keep Block Public Access, private encryption and TLS enforced. Reuse the restricted policy in [s3-runtime-policy.example.json](../s3-runtime-policy.example.json) with that bucket/prefix. Do not create a replacement bucket. Prefer an existing least-privilege EC2 instance role; on Oracle use a restricted existing S3 runtime identity in the private environment file. No S3 resource is provisioned by Compose.

## Environment variables

Copy `.env.example` **outside Git**, e.g. `/etc/invoiceguard/runtime.env`, owned by the operator and mode 600. The file is unquoted `KEY=value` format with no shell expansion/inline comments; do not `source` it. Compose's raw env_file protects literal dollar characters in provider secrets. `POSTGRES_PASSWORD` must be 64 lowercase hexadecimal characters generated by `openssl rand -hex 32`; do not change it after DB initialization without a deliberate password rotation. Do not print rendered `docker compose config` (it contains secrets); use `config --quiet`.

Required: `APP_IMAGE=invoiceguard-ai:<full-commit>`, `APP_DOMAIN`, `ACME_EMAIL`, `POSTGRES_PASSWORD`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `S3_BUCKET`, `AWS_DEFAULT_REGION`, `S3_PREFIX`, and a restricted AWS identity (instance role or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` with optional `AWS_SESSION_TOKEN`).

Extraction: `GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_API_KEY` for the existing provider path. Without the key, existing conservative standard extraction applies. A live Gemini result remains unverified until a run reports that provider and evidence checks complete.

Email Intake, if already configured: preserve `GMAIL_ENCRYPTION_KEY`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI=https://YOUR-DOMAIN/api/v1/email/oauth/callback`, `GMAIL_TRUSTED_ORIGIN=https://YOUR-DOMAIN`, `GMAIL_POLL_SECONDS=60`; verify that callback against the existing Google OAuth client and application route before changing it. Keep `GMAIL_USE_GEMINI=false` unless separately consented/configured. Reuse the exact encryption key if migrating encrypted connections; never copy plaintext tokens. Existing Gmail connections are workspace/identity bound and require a separate supported migration or new consent, not local identity copying. The always-on worker polls sequentially; it pauses during VM downtime. Existing Render Free polling also pauses while the instance sleeps.

Compose pins `APP_ENVIRONMENT=production`, `AUTH_MODE=supabase`, `STORAGE_BACKEND=s3`, `ALLOW_MANUAL_EXTRACTION_MODES=false`, `OMP_THREAD_LIMIT=1`, same-origin `FRONTEND_ORIGIN`, internal `DATABASE_URL`, and ephemeral staging `STORAGE_DIR`. Neither API nor worker relies on staging as original-document storage. Do not put secrets into frontend `VITE_` variables.

## Deploy on the selected VM

On a fresh VM only, clone to a separate directory, not over the working Windows checkout. Prepare the environment file using an editor/secrets manager; the example contains placeholders and is not deployable as-is.

```sh
git clone https://github.com/Deepakreddy1510/invoiceguard-ai.git
cd invoiceguard-ai
git switch main
git pull --ff-only
export VM_ENV_FILE=/etc/invoiceguard/runtime.env
git rev-parse HEAD
# Set APP_IMAGE in the private file to invoiceguard-ai:<that full commit>.
sh deploy/vm/deploy.sh
```

The script validates Compose without printing values, builds before downtime, starts the persistent DB, stops API/worker writers, creates a private pre-migration PostgreSQL dump, runs existing additive migrations under the existing advisory lock, then starts one API, one worker and Caddy. It never runs seeding/reset or cloud provisioning. An advisory deployment file lock prevents overlapping operator deploy scripts. Migration/backup failure leaves application writers stopped for inspection; no automatic downgrade is attempted. Caddy persists certificates and redirects HTTP to HTTPS. No access logs are enabled; application diagnostic logs remain sanitized. Docker log envelopes have timestamps/JSON fields and rotate at 3 × 10 MB per service.

For subsequent updates, record the old image tag, pull the reviewed commit, update APP_IMAGE, and rerun the same script. Do not use `docker compose down -v`, `volume rm`, database reset, dev seeds, or sample installer CLIs against this hosted database. The deployment uses project `invoiceguard-vm`, separate from development volumes.

Useful commands (repository root, VM_ENV_FILE exported):

```sh
docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml ps
docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml logs --since 10m api worker proxy
docker stats --no-stream
docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml restart api worker
```

Docker restarts exited containers independently; unlike the Free supervisor, worker exit does not terminate the API. A running but unhealthy worker is reported by its DB heartbeat check; Docker does not automatically restart a merely unhealthy process. Inspect the safe logs/dependency health before an operator restart. A stopped/killed worker may leave a lease for up to 180 seconds; normal token fencing and bounded recovery apply. Never start a second worker as a workaround or modify reservations to clear the queue.

### Backup and rollback

Private dumps are written beside the environment file under `backups/`. Copy encrypted backups off the VM under an agreed retention policy and test restore into a **separate** PostgreSQL instance. Preserve S3 originals, the Gmail encryption key and relevant configuration alongside the database backup. A Docker named volume survives container restart, not disk loss, VM deletion or free-instance reclamation. Disk encryption/access controls and off-host backup are operator responsibilities.

To roll back application code only, first stop API/worker, edit APP_IMAGE in the private file to the previously built immutable tag, confirm the previous version can read the **current migrated schema**, then:

```sh
docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml stop worker api
docker compose --env-file "$VM_ENV_FILE" -f deploy/vm/compose.yaml up -d --wait api worker proxy
```

Do not run the deployment script for a code-only rollback, because it rebuilds/checks the current commit and runs migrations. Never automatically downgrade or restore a dump over live financial history. If schema compatibility is uncertain, keep writers stopped and prepare a reviewed forward fix or a separate restore/cutover plan preserving all post-backup records.

## Demo workspaces and migration

For a new hosted account, existing signup/bootstrap creates **My Workspace**. Use **Create Workspace → Empty** to create equivalents of `sudhakar_pipes` and named personal/previous workspaces, and import that workspace's approved vendors and POs using supported UI CSV flows. Use **Create Workspace → Fictional sample** / **Create sample company** for an isolated Asterfield company; the existing worker generates genuine sample decisions/reservations and exposes progress. Use the existing fresh-demo functionality for a fresh fictional catalogue. Names may match local workspaces; IDs/history are new. Never claim these are copies of local financial records.

Exact historical migration is a separate operation: stop all writers; back up source/target independently; inventory workspace IDs, signed production subjects/membership mapping, documents/hashes/S3 keys, all invoice/revision/decision/allocation/reservation tables, audit and email state; copy immutable PDFs privately with hash verification; rehearse a transactional conflict-checked import into a separate restored database; verify balances, audit hashes/order and cross-account denial before an approved cutover. Existing IDs must be preserved for actual imported history, and conflicts must stop the import rather than overwrite hosted rows. Local `local-demo-reviewer` is not a production identity. A reviewed explicit mapping to the verified Supabase UUID is required. No bulk migration/reset script is provided or run in this change.

## Live acceptance

Follow [the exact single-PDF and batch acceptance procedure](../pdf-upload-verification.md). A healthy container or HTTPS 200 is insufficient. Complete login, source storage/retrieval, digital/OCR extraction, genuine validated/overbilling decisions, audit/history, restart persistence, account isolation and sequential responsiveness before publishing the URL as working. No public VM URL or acceptance success is claimed here.
