# Business UX and Asterfield sample company

This update preserves existing workspaces, documents, decisions, commitments, Gmail OAuth, extraction adapters and financial controls. No migration is required. The financial engine and `email-po-review-v1` are unchanged. Nothing is deployed.

## Product behaviour

Processing opens with the actual financial decision, recorded reasons and next action. Processing completion does not mean financial approval. Source values remain visible; each field has a disclosure for its exact evidence. Financial checks are deterministically grouped into supplier, completeness, purchase order, amounts/tax, and duplicates/authorisation. Missing prerequisites prevent a dependent group from being presented as fully passed. Individual recorded explanations and the immutable original rule records remain available.

The six business stages are invoice received, document read, details extracted, supplier/order checked, financial checks, and decision recorded. Supplier/order checking is a view of actual validation events and recorded rules, **not an additional backend event**; it has no fabricated duration. OCR appears only when a persisted non-skipped OCR event exists. Durations require matching start/finish events in the same attempt. Corrections show evidence reuse rather than a new PDF read. Queued stages remain pending. Run selection, polling, retry, review, source download and history are retained.

The PO comparison uses the exact matched PO record. Current order values are labelled separately from decision-time balances. Missing or ambiguous PO matches have an explanatory empty state. Structured email provenance is rendered as individual references, quotes and PDF evidence, never stringified objects.

Email Intake requests `view=actionable`; candidates and attachments needing attention are filtered in SQL before pagination. **All email activity** retains ignored and no-attachment messages. The existing API default remains `view=all` for compatibility. Current connection health is separate from the selected email's attachment activity. Original mailbox records are retained. Sync, reconnection, disconnect and reviewer controls remain functional; forwarding intake never approves financial expenditure.

Activity History retains `/audit`. Business view filters stored events before pagination, excluding routine heartbeats and stage chatter while retaining decisions, failures and workspace actions. Search includes recorded detail; actor/stage filters are server-side. Original audit records are paginated separately. Local identities are labelled Demo Administrator and Automated Processing. Technical details, raw JSON, hashes, provider metadata and complete events are collapsed and rendered only for an ADMIN workspace. This is a presentation restriction, not a change to existing backend authentication contracts: authorized workspace members retain existing API permissions.

PO matching now reads complete tokens such as `MAIL-PO-001`, `AF-PO-2026-001`, and `AST/PO/2026/001`. It does not uppercase, strip prefixes or equate separators. Repeated identical references are deduplicated within a source; conflicting references and email-only claims still require review. Gemini PO candidates must also be complete source identifiers. Unknown/unsupported Gemini responses retain conservative handling.

## Asterfield dataset

`backend/scripts/install_asterfield_demo.py`, version `asterfield-v1`, seed 20261106, creates **a separate local sample workspace**. It never renames or resets an existing populated workspace. Its deterministic identity is scoped to the version and local identity; concurrent installer invocations are serialized by an advisory lock. Hosted installation deliberately refuses to grant memberships automatically.

- 18 fictional vendors: 16 approved, one suspended, one inactive. Pinehaven suppliers have similar names but distinct supplier codes and explicitly fictional tax identifiers.
- 36 POs: 30 INR, two USD, two EUR, two GBP; 18 itemized, 18 amount-based. Initially 32 open, three closed and one cancelled. Partial status is set only on this new sample company's orders after actual validated commitments exist.
- 21 actual PDFs: 19 digital, one scan, one photographed derivative. Three panel/letterhead arrangements, seven documents each. Typographic supplier branding, retail supplies, logistics, services, tax-exempt training, explicit tax and one tax-inclusive printing invoice. Mostly INR; USD/EUR/GBP examples remain in their own currencies.
- Independently authored decisions: 14 VALIDATED, six BLOCKED, one NEEDS_REVIEW. Assertions verify actual worker decisions, OCR and every PO's consuming commitments/remaining capacity. No balances are seeded directly.
- No real logos, addresses, government tax registrations, bank details or payments. All prices and organisations are fictional. The sample-company disclosure remains visible.

`procurement.json` and `manifest.json` document the catalogue, seed, expected cases, layout/media and SHA-256 hashes. Generation is deterministic. Ordinary regressions verify the new presentation fixtures; **these are not a held-out benchmark**. Frozen synthetic-v2 development/evaluation fixtures and answers are unchanged. Success here is not evidence of real-world extraction generalization.

The installer explicitly requests FALLBACK, regardless of a locally configured Gemini key. It processes real PDF bytes through ingestion, worker, financial evaluation and persisted decisions. It verifies all balances before marking the workspace DEMO and preferred for a new session. Failed verification leaves an inspectable CUSTOM workspace, not a preferred demo. Repeat installations reuse the same idempotency keys/documents/runs and do not consume again. Changing extraction mode intentionally creates a new comparison run under existing application behaviour; use the same mode when demonstrating an exact replay.

## Windows CMD upgrade — existing repository and database

Run in CMD, not PowerShell. Keep the existing PostgreSQL volume, `.env`, Gmail tokens, Gemini key, OAuth origin and procurement history.

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai
git status --short
git diff -- compose.yaml
git stash list
git pull --ff-only origin main
```

This update does not change `compose.yaml`, so the user's uncommitted `127.0.0.1:5434:5432` mapping normally survives the pull. If Git refuses because of local edits, stop and inspect those paths; do not reset, clean, checkout over them or apply an old stash blindly. To temporarily protect an intentional compose-only edit, use:

```bat
git stash push -m "Preserve local Windows PostgreSQL 5434 mapping" -- compose.yaml
git rev-parse stash@{0}
git pull --ff-only origin main
```

Record the printed stash SHA. Then `git stash apply THE_RECORDED_SHA` (replace the placeholder), inspect the result with `git diff -- compose.yaml`, and leave that stash retained. If conflicts occur, resolve the compose mapping manually before starting services. Older stashes remain untouched; inspect `git stash show -p STASH_REFERENCE` before deciding whether any earlier Windows fix is still needed. Do not publish stash contents or `.env` output.

Verify locally that `compose.yaml` still binds host **5434** to container 5432 and that the existing ignored `.env` has `DATABASE_URL` pointing to that same host port. Do **not** replace `.env` with `.env.example`. Do not run another project/compose name against a fresh volume as a substitute for the user's database.

```bat
docker compose up -d db
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run python -m scripts.install_asterfield_demo
```

The installer prints its actual verification report and workspace ID. It is safe to rerun. It is local-only; running it against hosted/OIDC mode is rejected. No seed/reset command for the original workspace is needed.

Start API and worker in separate CMD windows:

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\backend
uv run python -m app.worker.main
```

Start the frontend in a third CMD window:

```bat
cd /d C:\Users\DELL\projects\invoiceguard-ai\frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

Open the Vite site **on the same Windows computer running those commands**, preserving the existing `http://localhost:5173` Gmail OAuth redirect origin. These commands do not make a Codex Cloud listener reachable from a laptop. No public preview URL is created. In the sidebar select **Asterfield Retail & Services · Sample company**. A remembered manual workspace selection takes precedence, so select it explicitly after installation; original Demo/My workspaces remain selectable. Do not change `LOCAL_WORKSPACE_ID` to move historical records.

For Windows OCR, install Tesseract English and ensure `tesseract --version` succeeds in the terminal that starts the worker/installer. Do not copy Linux-only paths into `.env`. Existing Gemini/Gmail credentials are retained; no test here claims they have been exercised live.

## Limitations and manual verification

This is local synthetic demonstration data with invoice dates in November 2026 and PO validity through 2027. Tax policy is illustrative, not GST/legal compliance. The photographed PDF is a deterministic raster/contrast/skew derivative, not an independently photographed real document. There are three professional panel layouts, not 21 independently designed suppliers. All currencies here use two decimal places; frozen regression coverage for JPY/KWD remains unchanged. Nonzero allocated adjustments, external settlement and real payment execution remain outside the application's supported workflow.

Credentialed Gmail delivery, live Gemini, hosted OIDC invitations and Windows execution must be verified in the user's configured environment. Provider-mocked Gmail tests exercise the real pipeline and database but are not live mailbox delivery. No secrets were needed for the synthetic verification. See the final verification record for executed commands and actual results.
