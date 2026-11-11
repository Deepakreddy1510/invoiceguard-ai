# Optional Email Intake

`ENABLE_EMAIL_INTAKE` controls the sidebar item, browser route, all `/api/v1/email` endpoints (including OAuth callbacks), worker Gmail polling, connection synchronization and attachment-ingestion jobs.

Hosted environments (`APP_ENVIRONMENT` other than `local`) default to **disabled** when the flag is omitted. Local development retains its previous enabled default. Set `ENABLE_EMAIL_INTAKE=false` explicitly to disable it in any environment, or `true` to opt back into the existing feature with its normal authentication, membership, configuration and consent checks. The public `/api/v1/config` response exposes only the resolved boolean as `enable_email_intake`; the browser defaults to hiding the feature unless it receives `true`.

When disabled, the sidebar has no Email Intake link, old `/email-intake` bookmarks redirect to Overview, and email API calls return a sanitized 404. Gmail work returns before querying the database, taking locks or contacting Google, even if credentials/connections are already configured. No credentials, pending messages, consent records or audit history are deleted. Already accepted invoice runs remain in the normal durable invoice queue and continue financial processing; disabling intake does not cancel or alter existing invoice records or reservations.

Manual PDF upload, sequential batch processing, Gemini extraction, source evidence, financial checks, Supabase login, workspace permissions and procurement remain unchanged. The Email Intake implementation and tests remain in the repository.

## Apply on Render

Deploy the new commit manually on the existing service (automatic deployment is disabled). Optionally set `ENABLE_EMAIL_INTAKE=false` explicitly in its environment or existing `invoiceguard-runtime` group. Keep the same value on both API and worker when deployed separately. Restart/redeploy both processes so cached settings reload. Do not change authentication, Google permissions, Gemini configuration, storage or database settings.

Verify `/api/v1/config` reports `enable_email_intake: false`, the sidebar omits Email Intake, and visiting `/email-intake` redirects to Overview. An authorized request to `/api/v1/email` must return 404. Upload a real invoice through the existing UI and confirm its recorded extraction stages, financial decision, original document and history still work. Existing enabled requests may finish during shutdown; after the processes restart, no new email discovery or ingestion is scheduled.

No deployment or live Google account operation was performed by this change. Local automated checks cover feature defaults/overrides, guarded endpoints, no-work background calls, preserved PDF processing, navigation and direct-route behavior.

## Verification

All 355 backend tests and 97 frontend tests passed. Backend Ruff lint/format, frontend ESLint/format, production build and secret scan passed. Provider calls in tests are controlled; no live Gmail or deployment action was performed.

## Complete disabled-feature UI coverage

The resolved flag is shared across the app so Overview, workspace Settings and historical-source panels use the same state as navigation. When disabled, Overview never requests intake statistics, Settings never mounts Gmail configuration, and intake links are excluded from source/history cards. Historical invoice/audit records remain stored; generic source labels avoid promoting the disabled integration. Workspace onboarding and help focus on manual PDF processing. The Overview chart and review panels fill two columns (one on narrow screens) with Recent processing activity directly below; there is no placeholder inbox card.

Old `/email-intake` URLs now redirect silently to `/` (Overview), discarding intake query parameters. Authentication-related confirmation, registration and password-recovery email UI remains unchanged. No processing backend, database or storage behavior changed in this frontend cleanup.

The disabled-feature cleanup also passed a Chromium regression at 1440px and 390px widths, checking the public-config boot, silent old-route redirect, responsive invoice layout, Settings and zero intake API requests. Browser responses are controlled test fixtures; the deployed site was not changed or verified by this run.
