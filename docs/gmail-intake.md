# Gmail intake: operation, setup and live-verification checklist

InvoiceGuard now has an actual Google OAuth/Gmail adapter, background polling, durable email/attachment intake, optional Gemini classification, source evidence, intake review and a React Email Intake page. Accepted PDFs use the existing ingestion, OCR/extraction, financial worker and exception workflow. There is no separate financial engine and no simulated email-arrival endpoint.

**Live Gmail and live Gemini are UNVERIFIED in this environment.** Automated tests use mocked provider transports, actual PostgreSQL, real PDF/OCR processing and the real financial engine. No real Gmail message was observed or sent. No service has been deployed, purchased or activated by this change. A dedicated test Gmail account and Google OAuth configuration are required to verify external delivery.

## What runs

A workspace ADMIN starts OAuth. The server issues a one-time, ten-minute state challenge bound to an HttpOnly SameSite cookie, the verified subject and workspace. Authorization-code exchange uses PKCE S256 and the confidential client secret. Callback processing rechecks ADMIN membership and a configured exact trusted origin. Access/refresh credentials and the PKCE verifier are encrypted with Fernet and bound to their workspace. React never receives these secrets. OAuth callback query strings are redacted from Uvicorn access logs; any hosting proxy/log drain must also redact them.

A successful first connection initializes the cursor from Gmail's **current history ID**, without listing old messages. The existing Python worker periodically reads new `INBOX` history. Message identities, normalized bodies and attachment tasks are committed before checkpoint advancement. Paginated history persists its page token; committed message prefixes are skipped after restart/failure. An expired history cursor recovers through bounded recent-inbox pages using the last synchronization/connection time, a small overlap and idempotent identities. Large history batches use the same bounded recovery. There is no automatic full-mailbox import or historical-backfill button in this version.

Each supported attachment is fetched once per attempt through Gmail's API, signature/size checked, read with PyMuPDF/Tesseract, and classified independently. Quotes and candidate fields are checked against the normalized subject, body, filename, sender or limited PDF text. Uncertain classifications, possible multiple invoices within one PDF, and conflicting/multiple PO references require intake review. Gemini is advisory: when explicitly enabled it must return the structured schema and supported quotes; otherwise conservative screening records FALLBACK and its reason. A PDF's ordinary PO field does not make it a purchase-order document: screening distinguishes document-type headings from invoice fields.

Accepted bytes enter `app.ingestion.ingest`. Document/run links and Gmail identities are committed atomically with the handoff, before another worker can claim the invoice run. The regular worker executes source verification and every existing vendor, status, tax, currency, duplicate, quantity and capacity control. Exact replay links the immutable earlier run; different-byte business duplicates still face the original identity rules. Unique invoice/document metrics do not increase from retries or replay.

Email Intake follows the latest persisted financial revision while retaining its original handoff run link. The UI separates intake disposition from processing state and financial outcome. **INGESTED** means a PDF was handed to the queue. **SUCCEEDED** means technical processing completed. **VALIDATED / NEEDS_REVIEW / BLOCKED** are persisted financial decisions; FAILED does not invent one. Real mailbox/attachment events, attempt-specific classification/review evidence and invoice execution events are retained and displayed. Original PDFs can be previewed for intake review; email HTML is normalized to text, never rendered as HTML or followed for external resources.

## Versioned email PO policy

`email-po-review-v1` stores email claims in `ProcessingRun.intake_context` and decision provenance, separate from the PDF extraction object. It can withhold automatic validation; it cannot grant capacity or turn BLOCKED into an approval.

- Verified PDF PO, agreeing email or no email reference: existing financial matching continues.
- Missing PDF PO with a subject/body reference: display real, workspace-scoped procurement candidates, but preserve the missing PDF field. The financial REQUIRED_PO rule still requires review; no automatic email-only reservation is permitted.
- Multiple or conflicting email/PDF references: intake review before forwarding. A reviewer can select a PO only from recorded, supported evidence and the authorized workspace. Forwarding still runs all financial controls. An unresolved conflict also adds an explicit financial review rule.
- Intake confirmation cannot fabricate PDF fields, change vendor status or authorize overbilling. Human financial corrections use the existing attributed exception workflow. Email provenance is inherited by retries, mode comparisons and review revisions.
- Exact replay retains an earlier immutable decision even if a later email has conflicting context. That email receives a separate intake-review disposition; it does not retroactively rewrite the old decision or create a commitment.

## Google Cloud setup — dedicated test account

1. In Google Cloud Console, create/select a development project, then **APIs & Services → Library → Gmail API → Enable**. Do this manually; this repository does not enable services or start a billing plan.
2. Open **Google Auth Platform** (OAuth consent screen). Configure Branding/support email and the required application details. Choose an appropriate audience. For a consumer Gmail development account, use **External → Testing** and add the dedicated mailbox address to **Test users**. Keep actual vendor/customer mail out of this initial account.
3. Under **Data Access**, request only:

   ```text
   https://www.googleapis.com/auth/gmail.readonly
   ```

   Do not add `gmail.modify`, `gmail.send` or full-mailbox mutation scopes. Gmail metadata-only permission cannot retrieve PDF bodies. `gmail.readonly` grants broad mailbox read access at Google's permission boundary; this application's polling selects INBOX messages. There is no OAuth scope restricted to one Gmail label.
4. Under **Clients → Create client**, select **Web application**, for a confidential server-backed application. This is a separate client from your existing Auth0 SPA. Set the exact authorized redirect URI:

   ```text
   http://localhost:5173/api/v1/email/oauth/callback
   ```

   Vite forwards this `/api` callback to FastAPI. Server exchange does not require a browser JavaScript client secret or a new SPA authentication flow. Use the **same exact origin** to open the frontend; mixing localhost and a different loopback hostname breaks the cookie binding.
5. Copy the client ID and client secret into your ignored repository-root `.env` as below. Do not put secrets into `VITE_*` variables, frontend source, screenshots, logs or GitHub.
6. Generate a new encryption key **once**, from `backend` in Windows CMD:

   ```bat
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Paste it into your ignored `.env`, then keep the same key on both API and worker. Back it up through appropriate secret management. Do not regenerate it at every startup. Losing/replacing the key makes existing tokens unreadable; revoke the app in the Google account and reconnect. This implementation does not provide an automatic multi-key rotation service.
7. Restart API/worker, choose the intended workspace, open **Email Intake → Connect Gmail**, and consent using the dedicated test account. The Google consent flow and backend callback must complete; the UI cannot fabricate a connection when configuration is absent.

Required settings for local use:

```dotenv
GMAIL_CLIENT_ID=your_google_web_client_id
GMAIL_CLIENT_SECRET=your_google_web_client_secret
GMAIL_REDIRECT_URI=http://localhost:5173/api/v1/email/oauth/callback
GMAIL_TRUSTED_ORIGIN=http://localhost:5173
GMAIL_ENCRYPTION_KEY=your_generated_fernet_key
GMAIL_POLL_SECONDS=60
GMAIL_USE_GEMINI=false
```

The first five values are required to enable connecting. Poll interval defaults to 60 seconds, constrained to 30–3600. Email AI is an explicit server-side opt-in. To test it with synthetic messages, set `GMAIL_USE_GEMINI=true`, configure the existing `GEMINI_API_KEY` securely, and retain `GEMINI_MODEL` (default `gemini-2.5-flash`). The UI shows the configured email classifier and each actual result records its provider/model/fallback reason. Invalid Gemini output/provider failure uses conservative screening; no live success is implied by configuration.

## Google verification and privacy limitations

Gmail read access is a **restricted scope**, rather than ordinary basic-profile access. A Testing OAuth app is intended for explicit test users, generally with a maximum of 100 listed test users. External Testing grants containing Gmail scopes normally have refresh tokens that expire after seven days; the basic-profile-only exception does not apply to this integration. The UI exposes expiration/revocation as AUTH_REQUIRED and supports reauthorization of the same mailbox while preserving its checkpoint.

An externally published app is a separate release process. Public use may require Google branding/domain/privacy-policy validation, restricted-scope verification, justification, demonstration, and a security assessment when restricted data is stored/transmitted on a server, subject to Google's applicable exceptions. Workspace Internal apps have organization/account restrictions and are not a shortcut to unrestricted consumer Gmail access. This project has **not** completed production Google verification or a security assessment, and does not claim arbitrary public Gmail connections are approved.

Before real non-synthetic data is used, confirm Google's current requirements, Limited Use policy and your provider/organization's data-handling obligations. Transferring mailbox content to Gemini requires appropriate disclosure, consent, provider terms and permitted data use; do not use a provider configuration that trains general models on restricted Gmail data. Email AI is off by default for this reason. Review production retention, access controls, log redaction and encryption/backups before rollout. Disconnecting retains historical email evidence and financial audit records; it is not a data-erasure mechanism.

References:

- [Gmail scopes and restricted-scope classification](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Google server-side authorization flow](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
- [Gmail history synchronization](https://developers.google.com/workspace/gmail/api/guides/sync)

The official Google Gmail discovery document was inspected for the read scope and history endpoint. These policy links are deployment prerequisites; this environment cannot perform the external verification process or attest to Google approval. Recheck current policy when publishing an OAuth app.

## Windows CMD upgrade and start

Stop your API and worker with Ctrl+C first. Substitute your checkout path and preserve any local work before pulling. These commands never reset a database, delete a volume or reseed your existing workspaces.

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

Migration **0008** adds Gmail connection/state/message/attachment/event tables and nullable run intake context; it does not alter original procurement data or financial history. Your existing Auth0/OIDC and `.env` configuration remain in place. Add the Gmail settings only after completing provider setup; without them manual PDF upload remains functional.

Start three separate CMD terminals:

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

Open `http://localhost:5173` **on that Windows computer**, matching the registered OAuth origin. This is a local execution instruction, not a Codex Cloud preview URL. The cloud environment exposes no forwarded browser preview. No public deployment is included. Existing prerequisites remain Python 3.12, uv, Node 24, Docker Compose and Tesseract English on the worker PATH. The real worker performs both polling and invoice processing; keep it running. Native Windows receives the IANA timezone database through the conditional `tzdata` dependency, and PDF extraction uses Unix OS resource caps only when that module is available. Existing subprocess timeouts, page/pixel/size limits still apply on Windows. Tests here ran on Linux; native Windows execution itself remains unverified.

## Live smoke test still required

Use a fresh private **My Workspace** (or intentionally unused synthetic authorization) so this check does not consume your prepared demo POs.

1. Create vendor **Mail Test Supplier (Synthetic)**, code `MAIL-001`, tax ID `SYNTHETIC-MAIL-001`, APPROVED, using the Vendors UI.
2. Create itemized PO `MAIL-PO-001`, USD, OPEN, dates covering today, authorization **220.00**; item SKU `PAPER-A4`, description synthetic cartons, quantity **10**, price **20**, tax rate **0.10**. Use current-year issue/valid-until dates.
3. Generate only local synthetic PDFs, from `backend`:

   ```bat
   uv run python -m scripts.generate_gmail_smoke_samples
   ```

   Output goes to the previously nonexistent `.local\gmail-smoke` directory; it does not overwrite regression fixtures or access a database. If it already exists, choose a new empty location with `--output`.
4. Connect the dedicated Gmail test account to this workspace. Once connection completes, send a **new** email to it from another controlled account with `valid.pdf` attached and subject/body mentioning `PO: MAIL-PO-001`.
5. Without downloading/uploading in InvoiceGuard, wait for automatic polling. Verify the message, classified PDF, provider and evidence, actual run events and VALIDATED decision. This should reserve **66.00**, leaving **154.00**, assuming this new PO had no previous consumption. Check the actual PO and audit views rather than inferring success from intake status.
6. Only after that first decision, email `overbilling.pdf`. Its **176.00** request should be BLOCKED by existing quantity/capacity rules, with no added consumption.
7. Resend the exact same `valid.pdf` file. Confirm a new source-email identity links the earlier immutable document/run and does not create another reservation.
8. Optionally send `scanned.pdf` (22.00) and verify actual OCR events. Test an unrelated brochure/quotation, mixed attachments, email-only PO, conflicting POs, and intake confirmation. Missing PDF PO should still require financial review.
9. Reload the UI and restart API/worker; verify persisted source, decisions, checkpoints and balances. Switch workspaces and confirm email data is absent elsewhere. Disconnect and verify reads stop, revocation eventually completes and existing financial history remains.

Record the real Gmail IDs, provider, run/decision IDs and balances from this smoke test. Until it is observed against real Google, Gmail delivery and token lifecycle are **UNVERIFIED**, regardless of mocked test results. Live Gemini likewise remains **UNVERIFIED** until the actual API is called successfully with source evidence inspected.

## Limits and failure behavior

- One non-retired Gmail connection per workspace, managed by ADMIN. Existing workspace membership is checked on each API request; the connection owner must remain ADMIN for background reads. Reviewers may disposition intake, but cannot manage credentials.
- PDF attachments only, up to 10 MiB each; at most 20 attachments/message, 100 MIME nodes and depth 8. Message API responses are bounded at 2 MB, body-part decoding at 64 KiB, normalized body at 12,000 characters. Classification uses at most two PDF pages/12,000 text characters. The full supported PDF still goes through the original up-to-20-page extraction and validation pipeline.
- Malformed/oversized messages are retained as failed intake identities, rather than blocking the cursor or fabricating a decision. Unsupported files are never executed. No email links, images or remote body resources are fetched.
- Pending active-mailbox PDF tasks are capped at 500 per workspace. HTTP timeouts, bounded discovery pages and per-attempt budgets provide backpressure. Provider failures use persisted exponential backoff (bounded to an hour), with at most five attachment attempts before FAILED. Reviewers can request an attributed retry. Synchronization continues after restart; session advisory locks prevent concurrent mailbox/attachment work, and abandoned SCREENING tasks become eligible again after three minutes.
- One worker processes bounded mail work alongside normal invoice jobs. Additional worker processes can share the same database/locks if needed; no new queue service is required. This is not a throughput or arbitrary-layout generalization claim.
- Disconnect immediately disables mailbox reads and queues provider revocation. Queued, unhanded-off sources become intake-review records; resend them to a newly connected mailbox or use manual upload. Existing downloaded invoice runs continue normally. Failed revocation retains only encrypted credentials for retry; restore server configuration or revoke manually in Google Account → Security → Third-party access if necessary.
- Original source preview requires an active authorized mailbox until an attachment is stored as an InvoiceGuard document. After handoff, existing authenticated original-PDF storage access works independently of Gmail connection state.
- An invoice with original immutable history is not silently deleted, rewritten, released or settled by an intake action. Historical financial amendments remain governed by the existing review/AP policy.

## Deployment prerequisites (no deployment performed)

Before a future authorized deployment, retain existing Auth0/OIDC invite/membership enforcement, shared PostgreSQL and private S3 storage for API/worker. Configure the same Gmail encryption key, Google confidential-client credentials, exact HTTPS trusted origin/callback, poll/AI settings and Gemini settings on the required processes. Register the exact HTTPS redirect with Google, complete any required provider verification/security assessment, configure data retention/privacy controls and query-log redaction, and perform the live smoke test with a dedicated synthetic mailbox. Do not expose local authentication publicly. No new paid infrastructure is required by this implementation.
