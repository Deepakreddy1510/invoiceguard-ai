# GitHub publication and hosted-preview preparation

Status date: 1 November 2026 (Asia/Kolkata). The owner authorized committing/publishing the verified implementation and preparing Render. Paid services remain subject to a current price quote and separate explicit approval. No hosted resources or public website have been created.

## Repository publication scope

Target: `https://github.com/Deepakreddy1510/invoiceguard-ai`, default branch `main`. Initial remote tip was `59141608406d19885b6711c34a3fc3e6ee6e354a`. Publish with a normal fast-forward push only; never force-push or bypass branch protection. If GitHub requires a pull request, publish a feature branch and follow that requirement. The connected HTTPS Git transport accepts read operations and the publication dry run; GitHub API/CLI access is separately unavailable in the current network configuration. A dry run alone does not prove a completed publication: verify the remote tip against the resulting local commit and report the actual commit in the delivery message.

Publication includes application source, lockfiles, migrations 0001–0006, original synthetic regression fixtures, synthetic-v2 inputs/development oracles, offline synthetic evaluation reports/infrastructure, component/browser/backend tests, Docker/CI and deployment configuration. Synthetic evaluation expected answers are offline benchmark assets, not credentials or application inputs; `.dockerignore` excludes the entire `evaluation/` and `datasets/` trees from runtime images. No user-supplied real invoices, attachments or runtime uploads are included.

Ignored/private material stays outside Git: `.local/` (uploaded documents, logs, receipts and test artifacts), `.env` and variants except the empty/public `.env.example`, credential/key exports, virtual environments, node_modules, compiled frontend, caches, database dumps/backups and browser reports. PostgreSQL remains bound to loopback inside Codex and is not copied or exposed. Reports can contain disposable database **identifiers** as provenance, never database files or credentialed connection URLs.

## Secret and file checks

A pinned Gitleaks 8.24.3 binary was downloaded from its official release over verified TLS and checked against the published SHA-256 checksum manifest. Candidate files were copied to an isolated scanner input containing only Git-eligible files, excluding ignored material. The initial scanner found 24 generic-key matches: every finding was independently checked to be a source-file SHA-256 string in evaluation JSON provenance, under four specific backend source paths. No credential values were printed.

`.gitleaks.toml` retains the default detectors and exempts only complete JSON provenance lines for those four known source paths with exactly 64 hexadecimal characters. It does not exclude report files or arbitrary keys. The reviewed scan passes. Additional filename and key-pattern checks cover private export/dump paths and common GitHub/Google/AWS/private-key formats. No real keys or generated private runtime assets were selected. The final staged index must be checked separately before commit, and the committed snapshot must be rescanned before push.

The publicly documented `local_demo_only` database password and synthetic SDK test credentials are deliberately non-production fixtures. They must never be reused for hosted PostgreSQL or S3. Hosted settings come from Render's private environment group and internal new-database connection, not Codex `.env`.

## Final execution checks

- Backend: **107 passed, zero failed**; one upstream Starlette/httpx deprecation warning.
- React: **four passed, zero failed**.
- Browser: **eight passed, zero failed**, final publication run 29.6 seconds with actual Chromium/API/worker/disposable PostgreSQL.
- Ruff lint and formatting passed (82 Python files after the added post-deploy verifier).
- TypeScript/Vite production build passed.
- Deployment YAML and S3 IAM-policy JSON parse; private PostgreSQL and disabled automatic deployment guards checked. Account-level Render schema/resource validation remains pending provider access.
- New `scripts.verify_hosted_preview` was exercised in an owned disposable database with the expanded synthetic catalogue: newly generated PDF VALIDATED with a real reservation, missing-number PDF NEEDS_REVIEW, original bytes/events persisted, API/worker restarted, then exact decision/event IDs and PDF hashes verified. The test database was removed. This was **local internal validation, not a public HTTPS test**.
- Existing application source hashes still identify the previous measured development evaluation; no financial rules were changed during publication preparation. See `docs/completion-verification.md` for honest extraction/decision metrics and remaining limitations.

## Deployment preparation

`deploy/render.yaml` contains one Docker web service (React + API), one separate worker, and one private PostgreSQL service. All use Oregon; AWS S3 region is `us-west-2`. Automatic Git deployments are disabled. Both services reference an **existing** private `invoiceguard-runtime` environment group, created/configured as described in `deploy/README.md`; no secret placeholders are placed in a Blueprint group. `deploy/s3-runtime-policy.example.json` grants only the document-prefix operations, including cleanup of interrupted multipart uploads, over TLS.

No live preview/forwarded port is available in this Codex task. No actual Render HTTPS origin exists. Provider pricing access returned HTTP 403 under the enforced network policy, so **no current dollar quote is claimed and paid activation is blocked**. Read the current Render web/worker/PostgreSQL/disk quote and AWS regional usage rates, show the owner the total/budget/duration, and obtain explicit approval before selecting Deploy Blueprint or creating billable storage. Auth0 Free/Hobby Render eligibility must also be confirmed in the owner's account.

An environment configuration draft was saved to permit the exact provider-documentation/API destinations `api.github.com`, `render.com`, `dashboard.render.com`, `api.render.com`, `auth0.com`, `aws.amazon.com` and `docs.aws.amazon.com`, retaining the existing package-manager presets. A secure `RENDER_API_KEY` requirement targets only `api.render.com`. Existing settings were preserved; no secret value was read or saved. The draft requires review/save/publication through Codex environment settings before it changes runtime access. The specific tenant, S3 endpoint and eventual preview hostname are added only when known.

The owner can sign in to Render, connect this repository and inspect the Blueprint/resource quote **without deploying**. Auth0 issuer/audience/public SPA client ID, invited user subjects, a private S3 bucket/restricted identity, approved billing plan quote and the eventual HTTPS origin remain necessary. Enter real credentials only in secure provider/environment settings; never in chat or GitHub. Full exact setup actions are in `deploy/README.md`.

After approval and credentialed deployment, run the verifier against the **actual** HTTPS origin with a securely configured reviewer token. Verify the fresh valid PDF, missing-field edge, source storage and restart receipt. Separately open the actual site in a browser, test Auth0 owner/evaluator sign-in and upload, verify workspace isolation, and only then supply the verified interactive URL. Live Gemini is pending a real optional key and is not claimed tested.
