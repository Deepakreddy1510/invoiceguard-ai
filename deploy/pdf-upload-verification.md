# PDF admission, batch uploads and hosting verification

## Findings and fix

The owner's live logs establish an **inspection subprocess wall-time timeout at 55 seconds**, returned as HTTP 422 before ingestion/storage/worker processing. They also establish memory at the 512 MiB cgroup limit and a high `memory.events max` count. Zero OOM/OOM-kill counters do not exclude reclaim pressure or prove the exact cause of the stall. The particular instruction/syscall that stalled on Render has not been profiled.

Two avoidable source-level costs were confirmed:

- Importing the PDF subprocess wrapper also imported native PyMuPDF into API and worker parent processes. Sample catalogue imports pulled it in again even when no sample PDF was being generated. Native imports now occur only in actual parsing/generation functions. The parsing child applies its existing resource limits **before** importing the native library.
- `read_pdf(extract=False)` decoded text blocks on every page before checking the `extract` flag. Admission now checks readable PDF/encryption, page count and each page's existing rendering geometry limit without text decoding, image rendering or OCR. Digital text/OCR, exact source evidence and financial validation still execute in the durable worker.

Subprocess isolation, 55-second wall timeout, 45-second CPU limit on supported Unix systems, 1.5 GB virtual-address ceiling, 20 pages, rendering-pixel bounds and 10 MiB admission limit remain. The timeout was not increased. Signature inspection reads five bytes instead of loading the entire upload again. Inspect failure creates no document/run/submission/reservation and removes its staging file; it no longer calls S3 deletion before any storage attempt. Successful S3 ingestion removes redundant local staging originals while retaining authoritative private S3 objects. Existing conservative commit-acknowledgement handling retains originals when a commit outcome is ambiguous.

Timeout HTTP 422 responses now provide a safe retry/contact-admin message. The frontend preserves that message, sanitizes HTTP 5xx responses and pauses the queue on connectivity/availability/auth failures. It never exposes subprocess paths, exception text, provider responses or memory diagnostics to users.

## Local resource evidence and limits

Matched x86_64 Docker probes importing API + sample-service modules changed peak process RSS from **231,956 KiB to 105,300 KiB** (approximately 227 to 103 MiB). A separate container with a hard **512 MiB RAM / 512 MiB RAM+swap** limit, with API and worker modules resident, completed five sequential real digital-PDF inspect/extract cycles and one scanned-PDF inspect/OCR cycle. Digital cycles took approximately 1.9–2.3 seconds combined; scanned cycle approximately 2.5 seconds. Cgroup peak reached **356,904,960 bytes (~340 MiB)**, with memory-event max/OOM/OOM-kill counters zero.

That probe used synthetic one-page PDFs, idle imported service parents and no live DB/S3/Gemini traffic. It is a useful resource-bound workload test, **not** an end-to-end Render load certification. Full API/worker/DB tests and SDK-stub S3 handoff are tested separately. A pathological 20-page scan, large word payload, simultaneous evaluator requests, provider latency or sample setup can use more resources. Render Free remains a constrained temporary demo, not a proven reliable host for arbitrary permitted PDFs. The prepared [VM alternative](vm/README.md) uses separate supervised containers on 8+ GB; Oracle eligible Always Free capacity is preferred, otherwise EC2 requires cost approval. Nothing was provisioned.

## Multi-PDF behavior

The existing New invoice modal accepts file-picker or dropped selections, up to five PDFs per batch, and shows filename, size, removable waiting files and per-file Waiting/Uploading/Processing/Completed/Failed states. One active sequential flow uploads through the existing authenticated `/api/v1/documents`, then waits for the actual terminal run before submitting the next file. It never adds OCR/Gemini workers. Completed entries show the genuine VALIDATED/NEEDS_REVIEW/BLOCKED decision and link to timeline/checks in a new tab.

Repeated clicks are blocked synchronously. Each file keeps its idempotency key and original extraction mode across uncertain upload retries. A known worker failure uses the existing run-retry API rather than uploading the PDF again. A dropped response after acceptance can be retried with the same key; existing hash deduplication still applies. HTTP 422 affects only its file; connectivity/HTTP 5xx/401/403 pauses the batch for explicit retry. If a poll cannot establish completion within five minutes, it pauses rather than overlapping another upload with unknown processing.

Workspace/account changes cancel the frontend queue and pending requests. Already accepted jobs remain durably stored and authorized in their original workspace. Refresh/navigation never automatically resubmits files: accepted jobs/results are recovered from invoice history; waiting file bytes must be selected again. Files and tokens are not copied to browser batch storage. Completing a batch refreshes run history; the dashboard loads actual persisted results on return. Financial BLOCKED is a completed decision, not a technical upload failure.

## Manual Render deployment

1. In the **existing Free service**, manually deploy this commit from `main`; automatic deployment is disabled. Do not apply the paid Blueprint, create services, change database/auth/storage configuration, or reset data.
2. Confirm deployed commit, readiness and fresh `event=services_started` / `event=resource_sample` logs. Keep production/Supabase/private S3 settings and the single worker. Do not configure `AUTH_MODE=local` publicly.
3. At `https://invoiceguard-free-demo.onrender.com`, sign in with a legitimate confirmed Supabase account, select an authorized isolated test workspace, and record UTC test time and deployment ID.
4. **First test one small real digital PDF**, with an approved matching vendor/PO and unused capacity. Expect HTTP 202, a QUEUED run, actual text/extraction/validation/decision events, then the correct financial decision. Open the original PDF and its quotes/page numbers. A health 200 or upload 202 alone is insufficient.
5. Correlate safe PDF/S3/worker logs with memory samples and Render exit events. If inspection still times out, capture resource counters before/after and do not raise timeouts or claim success. Move to the reviewed VM plan when Free limits remain unreliable.
6. Only after the single-PDF acceptance succeeds, test five sequential PDFs including a corrupt PDF and an overbilling PDF. Expect an individual failed upload, continuing valid uploads, real financial decisions and no simultaneous worker jobs. Test a failed-file retry and repeat-click prevention. Pause/retry during a temporary service interruption. Refresh while a run processes: accepted history must remain and no upload must replay automatically.
7. Restart API/worker through Render, then verify persisted decisions, original source PDFs and immutable history. Confirm no new reservations from exact upload replay and that a re-exported business duplicate produces the existing duplicate outcome. Sign in as a separate account and verify it cannot access the first account's workspace/run/PDF/audit history.

**The Render origin remains blocked by this execution environment's outbound proxy (CONNECT HTTP 403), and no Render runtime/account credentials or legitimate customer sessions are configured here. No hosted upload success is claimed.**

## Exact operator smoke commands

These operate on synthetic data and consume genuine synthetic PO capacity. Do not run against a real customer's catalogue. Use the existing UI to create a **fresh, empty isolated test workspace** (not an initializing Asterfield sample), import `backend/demo/procurement.json`'s first vendor/PO using the supported fields/API, or use the following authenticated API setup. The account must already have signed in/bootstrap membership. Configure a short-lived access token securely in `INVOICEGUARD_SMOKE_TOKEN`, never in command arguments, chat or GitHub. Use HTTPS and the actual deployment origin.

```sh
cd backend
export ACTUAL_ORIGIN=https://invoiceguard-free-demo.onrender.com
# For a VM, replace ACTUAL_ORIGIN with its actual HTTPS domain.
uv run python - <<'PY'
import json, os
from pathlib import Path
from uuid import uuid4
import httpx
origin = os.environ['ACTUAL_ORIGIN']
assert origin.startswith('https://')
headers = {'Authorization': 'Bearer ' + os.environ['INVOICEGUARD_SMOKE_TOKEN']}
with httpx.Client(base_url=origin, headers=headers, timeout=90) as c:
    def post(path, **kw):
        r = c.post('/api/v1/' + path, **kw)
        if not r.is_success:
            raise RuntimeError(f'{path}: HTTP {r.status_code}; inspect privately')
        return r.json()
    post('workspaces/bootstrap')
    result = post('workspaces', json={'request_id': str(uuid4()), 'name': 'Hosted acceptance · Fictional sample', 'workspace_type': 'EMPTY'})
    wid = result['workspace_id']
    # Save the new workspace ID immediately; reruns deliberately create another workspace.
    Path('../.local').mkdir(exist_ok=True)
    Path('../.local/acceptance-workspace.txt').write_text(wid)
    c.headers['X-Workspace-ID'] = wid
    source = json.loads(Path('demo/procurement.json').read_text())
    po = source['purchase_orders'][0]
    vendor = next(v for v in source['vendors'] if v['id'] == po['vendor_id'])
    v = post('vendors', json={k: vendor[k] for k in ['code', 'legal_name', 'tax_id', 'status']})
    payload = {k: po[k] for k in ['number', 'currency', 'status', 'issued_on', 'valid_until', 'billing_mode', 'authorized_gross']}
    payload['vendor_id'] = v['id']
    payload['items'] = [{k: ('0' + i[k] if k == 'tax_rate' and i[k].startswith('.') else i[k]) for k in ['sku', 'description', 'quantity', 'unit_price', 'tax_rate']} for i in po['items']]
    post('purchase-orders', json=payload)
    print('Created isolated synthetic acceptance workspace:', wid)
PY
uv run python -m scripts.verify_hosted_preview \
  --origin "$ACTUAL_ORIGIN" --workspace "$(cat ../.local/acceptance-workspace.txt)" \
  --workflow --include-ocr --include-overbilling --receipt ../.local/hosted-smoke.json
# After an operator restart, verify saved decisions, event IDs and original hashes:
uv run python -m scripts.verify_hosted_preview \
  --origin "$ACTUAL_ORIGIN" --verify-receipt --receipt ../.local/hosted-smoke.json
```

The command creates actual PDFs and expects VALIDATED, NEEDS_REVIEW, VALIDATED (OCR) and BLOCKED (overbilling), checks events/financial reservation, source bytes and anonymous document denial, and saves a token-free receipt. It fails if outcomes differ; inspect evidence/current balances rather than weakening rules. It uses Automatic extraction: confirm the provider in run details if Gemini integration is part of acceptance. Run `uv run python -m scripts.verify_gemini_extraction --help` for the existing provider-specific local probe; no live Gemini call was made here.

Separately use two legitimate confirmed accounts in the browser: attempt the first workspace UUID in `X-Workspace-ID` with the second account (expect 403), and request its run/document without that header (expect 404). Do not grant the second account membership as part of this isolation test. The automated smoke command does not prove SMTP, Supabase browser callbacks or real cross-account consent.

## Focused verification results

- 121 distinct backend tests passed across admission, private S3 adapter/handoff, API/worker, signed authentication, workspace security, procurement, resource diagnostics, Free supervision, financial/transaction rules, VM contract and the extended smoke command.
- 37 focused frontend tests passed (upload queue, workflow, request/workspace handling and existing authentication).
- One Chromium protocol/UI test passed, including partial rejection, individual retry, server-derived decisions and refresh while an accepted job remains processing. HTTP responses are controlled in that browser test; it is not a live-provider workflow claim.
- Backend Ruff lint/format, frontend ESLint/format and TypeScript/production build passed. The existing large PDF viewer bundle warning remains.
- The existing Dockerfile built successfully on x86_64. Caddy validated the new HTTPS configuration. The 512 MiB synthetic process probe described above passed. Arm64 execution, real S3/IAM, real Gemini, Supabase SMTP/browser login, Render upload and VM deployment remain live checks.

No backend financial/evidence rules, authentication grants, Gmail scopes/consent, paid Blueprint, Free Blueprint, development Compose or root Dockerfile were changed.
