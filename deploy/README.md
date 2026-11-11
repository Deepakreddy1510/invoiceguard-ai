# Controlled development hosting

For a separate **Free-only temporary assignment demo**, see [render-free-demo.md](render-free-demo.md) and `render-free-demo.yaml`. The paid Blueprint below is unchanged.

No deployment has been performed. This task's runtime reports no preview or forwarding capability. Binding `0.0.0.0` enables listening but does not make Codex reachable from your laptop. Do not use local authentication behind a public tunnel.

The prepared option is **Render Docker web + worker + managed PostgreSQL, Supabase login, and private AWS S3**. React is served by the API on the same HTTPS origin; Vite is not a production service. `render.yaml` is a reviewable Blueprint; provider plan availability, current charges and external provisioning must be validated in the owner's account. Starter web/worker and basic PostgreSQL are named, not purchased. No estimated price is asserted.

## Required approval and credentials

GitHub publication and deployment preparation are authorized. Paid resources are **not** authorized: first show the current service and usage price quote and obtain explicit approval. Use the verified published revision recorded in `docs/publication-verification.md`; connecting Render to an older revision will not deploy this implementation. Never force-push to bypass repository protection.

The owner must supply/configure, through provider secret settings:

- A Render account, GitHub repository authorization, approved region/service plans and billing approval if required. PostgreSQL remains internal (`ipAllowList: []`). No development database is exposed or copied.
- A Supabase project with Email provider, confirmation enabled and asymmetric signing keys. See [customer access](../docs/customer-access.md) for public runtime settings and exact redirect URLs.
- A new private S3 bucket, region and restricted runtime identity. Block all public access, enable encryption/versioning, require TLS. Grant only `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:AbortMultipartUpload` for `arn:aws:s3:::BUCKET/invoiceguard/*`. The app does not require public bucket access or runtime bucket creation. Use a dedicated short-lived identity where supported; otherwise store a restricted access key/secret only in Render's secret env group. Do not send credentials in chat, commit them or embed them in React.
- Optional Gemini API key with appropriate quota/billing. Blank means fallback. No live Gemini claim until a real verified response is observed.

This Codex task also restricts outbound hosts. Render API/dashboard, the selected Supabase project, S3 bucket endpoint and Gemini API need approved network access if deployment or live verification is to be performed here. Never bypass the session proxy or TLS policy.

## Cost gate (before resource creation)

This is the smallest **always-on topology in the prepared Blueprint**: one Starter web service (React + API), one Starter worker and one Basic 256 MB PostgreSQL service, all in Oregon. No separate static frontend service, Redis, custom domain, paid Supabase tier or Gemini is required. PostgreSQL disk and S3 usage are additional. This is a proposal, not a verified current price or a charge authorization.

| Resource | Proposed quantity/plan | Current price status |
| --- | --- | --- |
| Render web | 1 × Starter | Read the owner's current dashboard quote before approval |
| Render worker | 1 × Starter | Read the owner's current dashboard quote before approval |
| Render PostgreSQL | 1 × Basic 256 MB, smallest supported disk | Confirm compute + disk + backup charges in the quote |
| Render workspace | Hobby if eligible | Confirm no paid workspace tier is selected |
| Supabase | Free if eligible for this evaluator demo | Do not choose a paid tier or trial that auto-converts |
| AWS S3 | Private bucket, small synthetic PDFs | Usage based; show regional storage/request/transfer rates and proposed budget first |
| Gemini | Unconfigured | No Gemini API charges until separately configured/authorized |

Official pricing pages: https://render.com/pricing , https://auth0.com/pricing , https://aws.amazon.com/s3/pricing/ . This cloud task currently cannot fetch those provider pages (restricted egress; Render pricing returned 403). **No current dollar total is asserted and no paid plan can be activated until the quote is obtained and approved.** Account eligibility, taxes, workspace seats, PostgreSQL storage, transfer, build minutes and S3 requests can change the total. Review a monthly ceiling and intended demo duration, then remove resources only after preserving any required history. A billing budget/alert is not a hard spending cap.

Render's free web option can reduce compute cost if offered, but sleeps/cold starts and restrictions on predeploy commands/private shell access require a different tested startup procedure. Expiring free PostgreSQL is inappropriate for promised persistent evaluator history. The current prepared configuration preserves separate working services and reliable restarts; no untested free-tier substitution is made.

Automatic Git deploys are disabled (`autoDeploy: false`) to prevent future pushes from triggering hosting changes. Creating/applying a Blueprint still provisions its named resources: **do not select Deploy Blueprint until price approval is recorded**.

## Exact account setup before deployment

1. Sign in to Render at https://dashboard.render.com/ using the owner's account. Authorize its GitHub integration for **only** `Deepakreddy1510/invoiceguard-ai`. Select a Hobby workspace if eligible; do not activate an upgrade. Locate New → Blueprint and select the repository and `deploy/render.yaml`. Review the price/resource preview, but do not deploy. If the dashboard requires creation before showing costs, stop and use the pricing page/provider support instead.
2. Configure the intended Supabase project using [customer access](../docs/customer-access.md). Do not create paid infrastructure. Each signup receives a private workspace; preserve the current PostgreSQL database.
3. In AWS, review S3 regional pricing and the agreed budget before creating billable storage. After approval, create a general-purpose bucket in **us-west-2** to match Render Oregon; use a unique bucket name, keep all Block Public Access options enabled, bucket owner enforced/no ACLs, and default SSE-S3 encryption. Configure versioning/retention deliberately (versioned objects can continue incurring storage charges). Configure a least-privilege runtime identity with `deploy/s3-runtime-policy.example.json`, replacing only the bucket placeholder. Keep account/admin keys out of Render. Create restricted access keys only if a supported workload identity is unavailable; enter them directly into the shared Render secret group, not chat or GitHub.
4. In Render → Environment Groups → New Environment Group create **invoiceguard-runtime**. This existing group is referenced by both services; secrets are not represented as `sync:false` placeholders inside a Blueprint group. Add:

   | Variable | Value/source |
   | --- | --- |
   | `APP_ENVIRONMENT` | `production` |
   | `AUTH_MODE` | `supabase` |
   | `STORAGE_BACKEND` | `s3` |
   | `SUPABASE_URL` | HTTPS project origin |
   | `SUPABASE_PUBLISHABLE_KEY` | Public `sb_publishable_...` key |
   | `S3_BUCKET` | New private bucket name |
   | `AWS_DEFAULT_REGION` | `us-west-2` |
   | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Restricted runtime identity; secret values only in provider settings |
   | `GEMINI_API_KEY` | Omit/leave blank; fallback works without it |

   Do not manually set `DATABASE_URL` in the group: the Blueprint injects the new internal PostgreSQL connection separately into both services. Never use the Codex database URL. Do not set `S3_ENDPOINT_URL` for real AWS S3.

## Provisioning order after price approval

1. Publish only the reviewed implementation to the authorized repository/branch, excluding `.env`, `.local`, credentials and runtime data. Evaluation answers remain out of runtime images.
2. Configure Supabase Auth (see [customer access](../docs/customer-access.md)) and private S3 resources. Create the `invoiceguard-runtime` environment group above and supply its private values; the Blueprint intentionally does not contain group secret placeholders. Set `GEMINI_API_KEY` blank if unavailable. Keep `APP_ENVIRONMENT=production`, `AUTH_MODE=supabase`, `STORAGE_BACKEND=s3` for **both** services.
3. In Render choose **New → Blueprint**, select the repository and `deploy/render.yaml`, review the resource list/plans, then create only after approval. The web predeploy step runs `alembic upgrade head`; worker retries dependencies while migrations are pending.
4. Set Supabase Site URL and exact confirmation/recovery redirect URLs to the actual HTTPS application origin, following customer-access.md.
5. Preserve existing records and workspaces. New Supabase accounts automatically receive empty private workspaces; they do not inherit historical memberships. If explicitly authorized to join a shared workspace, use `scripts.provision_access` with the verified Supabase user UUID. Do not seed or reset the existing database.
6. Verify HTTPS `/api/v1/health/ready`, real React root and deep links, public `/api/v1/config` (public identifiers only), and that anonymous dashboard, review, audit and document requests return 401. Sign in as the owner and evaluator separately; verify workspace isolation, real PDF upload, OCR, correction and balances. Restart the web/worker and confirm history and original S3 PDFs remain. Check worker heartbeat. Confirm S3 public access is denied. Avoid destructive database resets.
7. Only after those checks share the actual verified HTTPS address and individual invitation instructions. The evaluator opens that address, chooses **Sign in securely**, uses their own invited account, and uploads via **Process Invoice**. No localhost, API key or database password is given to the evaluator.

## Local deployment artifact checks

```sh
docker build -t invoiceguard-ai:review .
```

The optional `ca_bundle` BuildKit secret supports managed corporate trust; do not disable certificate validation. The image installs Tesseract, runs nonroot, serves compiled React and uses the same image with `python -m app.worker.main` for the worker. Health checks use `$PORT`. The image excludes datasets, expected answers and runtime secrets. Hosted startup fails closed without Supabase/shared-storage configuration.

Local container and S3-compatible emulator results are documented in `docs/completion-verification.md`. They do not verify real AWS IAM/encryption, Supabase project settings, Render plan syntax against an account or a public HTTPS deployment. Treat those as release checks requiring the above authorization and credentials.

## Scripted post-deploy checks

From `backend`, run `uv run python -m scripts.verify_hosted_preview --origin "$ACTUAL_PREVIEW_ORIGIN"` after setting that non-secret variable to the **real** provider HTTPS origin. This verifies React/database readiness and anonymous access denial; it does not claim successful login.

For the real upload workflow, use a securely configured short-lived reviewer access token in `INVOICEGUARD_SMOKE_TOKEN` (never command arguments, chat, receipts or GitHub). Run the same command with `--workflow --receipt ../.local/hosted-smoke.json` against a newly seeded synthetic workspace with sufficient PO capacity. It generates a fresh valid PDF and a missing-number edge case, requires VALIDATED/NEEDS_REVIEW respectively, and verifies original bytes and actual persisted events. Repeated invocations consume real synthetic PO capacity; use the saved receipt for read-only rechecks rather than repeatedly adding invoices. An existing repeated-amount near duplicate can properly cause review; investigate the actual source/balances instead of weakening rules.

After restarting web/worker in Render, run the command with `--verify-receipt --receipt ../.local/hosted-smoke.json` to verify history and source persistence. Receipts remain ignored local files. Separately perform actual Supabase sign-in and upload in the browser as owner/evaluator; an HTTP smoke script does not establish that browser OAuth callbacks work. These HTTPS checks cannot be executed until a real hosted origin and authorized access exist.

For Codex-assisted provisioning, create a Render API key under Account Settings → API Keys and enter it only in the prepared environment secret requirement `RENDER_API_KEY` (destination `api.render.com`). Review/save the prepared network draft and publish the cloud environment to enable the provider destinations. This grants API access, not paid-plan approval. Supply the exact Auth0 tenant, bucket region/hostname and eventual preview hostname so their specific egress can be added when known.
