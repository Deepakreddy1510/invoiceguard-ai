# Free demo upload/restart investigation

**Historical investigation:** the owner subsequently supplied inspection-timeout and memory-pressure evidence. See [the current PDF fix and verification report](pdf-upload-verification.md) for the implemented admission optimization and batch UI. Hosted success remains unverified.

## Status

The deployed single-PDF failure remains unresolved. This investigation could not reach the Render origin: the execution environment's outbound proxy rejected CONNECT with HTTP 403. That is not a response from Render. Render runtime logs, exit events and memory graphs were unavailable. No live upload, S3 operation or deployment was performed. Multi-PDF upload is deliberately deferred until the single-PDF failure is resolved and verified.

One source-level inefficiency was confirmed and fixed: every run-summary poll loaded the complete OCR page JSON even though summaries do not use it. The summary query now defers that column; invoice detail still returns pages and events. A focused integration test verifies both the SQL projection and retained detail behavior. This reduces unnecessary polling memory/database traffic, but does not establish the cause of the deployed restart.

## Diagnostics added

The Free supervisor logs service startup, resource samples every 15 seconds, shutdown signals and child exit codes/signals. Samples include available numeric cgroup memory limits, current/peak memory, OOM counters and process RSS. Missing kernel metrics are tolerated. PDF subprocess failures log only stage, exception class and return code. S3 upload/download failures log only operation, allowlisted error category and HTTP status. These logs exclude invoice contents, object names, credentials and raw provider responses.

Existing behavior is preserved: one API process and one processing worker; a child exit stops its sibling and returns failure for Render to restart. Durable leases, retry fencing, financial checks and private S3 storage remain unchanged. Neither Blueprint is modified.

## Next verification on Render

1. Manually deploy the latest commit on the existing Free service. Its Blueprint disables automatic deployment. Do not create another service or select the paid Blueprint.
2. Record the deployment ID and UTC time. Check `/api/v1/health/ready`, sign in with an authorized test account, and upload exactly one small synthetic PDF in the intended workspace. Keep its run ID; do not put customer PDFs or secrets in logs or GitHub.
3. Collect runtime logs spanning the upload and restart, plus Render's process exit reason and memory graph. Look for `event=services_started`, `event=resource_sample`, `event=child_exit`, `event=shutdown_requested`, `PDF subprocess failed`, and `S3 operation failed`. Redact any unrelated sensitive log data before sharing.
4. Compare OOM counters before/after with Render's OOM events. SIGKILL alone does not prove memory exhaustion. If the entire container is killed, its supervisor may never emit a final exit log. A small compressed PDF also does not establish low OCR peak memory.
5. A sanitized S3 error identifies a storage failure category, not a demonstrated process crash. Correlate its timestamp with worker/web exit events. `X-Render-Routing: no-deploy` alone does not establish the underlying cause.
6. After a cause-specific fix, repeat a single-PDF upload through completion; verify stored PDF retrieval, expected evidence/financial results, audit history, stable worker heartbeat and absence of restarts. Only then implement and verify the sequential five-PDF frontend queue.

## Local verification

From the repository root:

```sh
cd backend
.venv/bin/pytest -q tests/application/test_runtime_diagnostics.py tests/application/test_render_free_demo.py tests/application/test_storage.py tests/phase2/test_api.py tests/phase2/test_transactions.py
.venv/bin/ruff check app scripts tests migrations
cd ..
npm run build
```

These checks passed (21 focused backend tests). They do not verify the deployed upload or certify that the full workload fits Render Free memory limits.
