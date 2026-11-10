# Customer product audit and PS-1 improvements

This audit starts from main commit `cee9728` and follows the current React → FastAPI → PostgreSQL/worker architecture. It is an implementation and local real-service audit, not a claim that the service has been deployed or that live Google/Gemini integrations have been certified.

## Prioritized implementation

1. **Essential navigation and safe recovery:** workspace controls have consistent spacing. Creation now uses the existing native dialog with keyboard focus handling. Collapsed desktop navigation moves the workspace selector, Create Workspace and Workspace Settings into one header row; account actions remain available. The sidebar selector's inherited margins were inflating the header. The same 1440-pixel browser measured approximately 193 pixels before and 67 after. Native 100/125/150/200% zoom is covered.
2. **Queue organization without ledger mutation:** migration `0011` adds nullable `invoice_documents.archived_at`. Active, Archived and All queue filters are available. Authorized reviewers/admins explicitly archive/restore documents; every processing attempt for that document follows the same visibility. PDFs, submissions, decisions, revisions, reservations, settlements, reviews and original audit records remain intact. Idempotent repeats do not add redundant audit events. Archiving adds an audit event only when visibility changes.
3. **Clear manual procurement:** Create Vendor and Create Purchase Order remain primary actions; the existing CSV import stays collapsed and secondary. Supplier forms explain legal identity and approval responsibility. PO guidance explains supplier/number, dates/currency, quantities/prices, fractional tax, spending limits and billing modes. Downloadable CSV templates now have readable column explanations and still use the existing all-or-nothing server preview/commit validators.
4. **Truthful invoice reading:** details separate Digital PDF text/OCR from Standard/Gemini extraction, show the actual Gemini model only for that provider, explain fallback and retain source evidence and technical metadata. Financial decisions remain deterministic. Gmail configuration distinguishes AI requested from AI actually available; it does not enable AI or change any provider setting.
5. **Conservative uncertainty fix:** explicit multi-PO source references were discarded during normalization. A clear PO elsewhere could then be selected without accounting for the ambiguous reference. Such references now remain conflicting source evidence. Standard extraction leaves the PO unresolved; evidence verification will not verify a convenient Gemini-selected PO against conflicting source text. New tests exercise actual PDF reading, the worker and zero-capacity-consumption outcomes.

## Current-state functional audit

| Screen or service | Current behavior and audit finding | Result / evidence |
| --- | --- | --- |
| Authentication and signup | Supabase email/password, confirmation, recovery and password visibility already exist. Server JWT signature/issuer/audience/session checks and membership determine access. | Retained; auth unit tests, controlled-provider browser flow and signed-JWT backend authorization tests. Live account registration is outstanding. |
| First login | Bootstrap creates a private empty My Workspace; MY/CUSTOM dashboards offer supplier/PO setup links. | Retained. Manual procurement and invoice acceptance flows are exercised in browser tests. |
| Workspace creation/switching | Empty and fictional Sample types use the existing PostgreSQL workspace model; UUIDs identify records even when names repeat. | Creation is now a dialog, available from expanded and collapsed navigation. ADMIN membership/ownership still comes from server-verified identity. |
| Sidebar/header | The complete selector inherited sidebar margins inside the collapsed header. Inline creation could also expand navigation substantially. | Compact header and modal creation; expanded/mobile navigation retains scrolling, visible keyboard focus and workspace settings. |
| Overview | Dashboard separates unique invoices, processing runs and duplicate assessments. Financial totals include all history. | Retained, including archived invoices. Archiving does not make historical capacity disappear. |
| Invoice Processing | PDF upload, filtering, pagination, durable run selection and retries already work. Deletion is intentionally refused. | Active/Archived/All queue views plus archive/restore confirmation. Upload copy explicitly supports scanned PDFs. Archived evidence remains directly viewable. |
| Invoice decision details | Stage summary and immutable attempt timeline already distinguish technical completion from a financial decision. Reading/provider wording previously conflated two steps. | Reading method, actual extraction provider/model and fallback reason are separate. Source-backed facts, PDF preview and financial checks remain available. |
| Exception Review | Versioned reviewer corrections create derived runs; source evidence and financial holds remain protected. | Retained. A review cannot override a hard financial block, and archive is not a disposition or release. |
| Email Intake | Read-only Gmail OAuth, bounded MIME/screening, source evidence, forwarding and workspace isolation already exist. | Added requested/available AI configuration disclosure. Each classification/run still records its actual provider and fallback; no configuration is changed automatically. |
| Vendors | Primary Create Vendor, protected legal identity after use, approval statuses and atomic CSV preview already exist. | Added supplier-oriented field guidance and explicit human approval responsibility. No document creates an approved supplier. |
| Purchase Orders | Primary manual creation, decimal calculations, itemized/amount-based limits, cumulative balances and CSV preview already exist. | Added field-by-field guidance and readable template column explanations. Validation and commitments are unchanged. |
| Settings | Versioned workspace rename/archive/restore and email privacy information exist. | Retained; a renamed sample remains visibly fictional. Workspace archive is separate from invoice queue archive. |
| Activity History | Workspace-scoped, persisted business/technical audit records are filterable and paginated. | Retained. New queue visibility actions append audit events; old records are not rewritten. |
| PDF preview | Authorized original PDF streaming and a PDF.js reader with page/zoom controls already exist. | Retained for active and archived documents; cross-account requests remain denied. |
| Backend worker | Durable PostgreSQL claims, expired lease reclaim, attempt limits and stale-worker fencing already exist. | Retained. No historical stage is fabricated or rewritten. |

## PS-1 coverage matrix

| Requirement / edge | Implementation and verified path |
| --- | --- |
| PDF → extraction → decision, visible real stages | `app/ingestion.py`, `app/extraction/pdf.py`, worker, `RunDetails.tsx`; real upload/worker/browser tests and 21-PDF sample initialization. |
| Several valid invoices against one PO, then over-budget | Existing financial transaction tests, `e2e/complete.spec.ts`, sample partial-order sequence. Blocked invoice creates no extra consuming commitment. |
| Different-byte business duplicate | Existing identity/financial tests and `e2e/workflow.spec.ts`; new archive test proves hidden originals still prevent double consumption. |
| Missing invoice number/reference | Existing workflow/sample tests; uncertainty leads to review. |
| Missing total and ambiguous PO | New `test_ps1_source_pipeline.py` uses actual generated PDFs, PDF reader and worker; no financial commitment is created. Conflicting Gemini evidence also cannot verify the PO. |
| Scanned/photo-based PDF and OCR uncertainty | Real Tesseract tests, scanned upload browser case, sample scanned/photo scenarios. Unverified fields do not validate. |
| Tax inclusive/exclusive | Existing validation/evidence tests and actual inclusive Asterfield source PDF. Saved financial rules are unchanged. |
| Itemized / amount-based bundled budgets | Existing procurement and financial tests, sample service orders, manual PO browser creation. UI now explains the difference. |
| Suspended/inactive supplier | Actual sample supplier scenarios and financial regressions; no approval is invented. |
| Closed/cancelled PO, currency mismatch | Sample closed-order PDF; new real-PDF cancelled/currency worker tests; existing financial engine regressions. |
| Technical failure vs block vs review vs validation | Existing worker failure/retry tests, full browser workflow suite, separate processing/financial statuses and original timeline. |
| Empty company → manual supplier/PO → invoice | `e2e/zzzzz-customer-ps1.spec.ts` creates the company, manually saves supplier and PO, uploads a real PDF and checks source/provider/financial outcome. Existing scanned upload runs through the real worker separately. |
| Used sample → fresh clean sample | Existing safety checks stay in `sample_service.start`; new selected-workspace start endpoint checks server-created provenance/ownership and ADMIN access. Backend and browser tests retain the old invoice/email/PDF and process 21 scenarios in the new workspace. |
| Import errors are atomic | Existing procurement preview/commit tests detect duplicate/invalid rows and leave no partial records. No client-only import path is added. |
| Cross-account isolation | Full signed-JWT backend regressions cover workspaces, PDFs, procurement and Gmail; archive/restore adds explicit owner-workspace and viewer denial tests. |
| Archive keeps ledger/history | New tests compare persisted decisions, commitments, revisions, invoice identities, events and POs before/after archive and restore. Original PDF bytes match. The existing migration preservation tests also run against the new head. |

## Safe sample recovery and queue semantics

`POST /api/v1/workspaces/sample-initialization/start` acts on the authenticated selected workspace. Existing documents, commitments, Gmail connections/authorization history or modified fixed procurement still prevent backfill. The UI explains the history conflict and offers **Create Fresh Sample Workspace**, preselecting Sample but requiring a name and explicit creation. It does not delete, archive, rename or reset the old workspace to get around the restriction.

`POST /api/v1/documents/{id}/visibility` accepts `{ "archived": true }` or `false`. It requires REVIEWER/ADMIN and the current workspace. `GET /api/v1/runs?visibility=active|archived|all` defaults to active; direct authorized run/PDF access is unchanged. All financial calculations, duplicate checks, sample-history checks and dashboard totals still include archived records. Uploading the same bytes does not automatically unarchive a document. Use Restore invoice to queue explicitly.

## Verified AI extraction and fallback behavior

The preserved pipeline is **PDF text / Tesseract OCR → Gemini or Standard extraction → source evidence verification → saved procurement and deterministic financial rules → decision**.

- `AUTO`: uses Gemini only when a key is configured. Missing key/provider error/invalid structured output uses conservative Standard extraction, with recorded reason. Unknown values stay unknown.
- `FALLBACK`: explicitly uses Standard extraction, with no Gemini model recorded.
- `GEMINI`: a required provider or evidence failure becomes a technical failure; it does not quietly report AI success or financially validate unsupported fields.
- Actual model/provider metadata is recorded by `pipeline.py`. An AUTO provider failure records the attempted Gemini model separately while keeping successful provider Standard and successful model null; UI configuration is not evidence of a successful call. Browser records here use real Standard extraction; Gemini success/failure paths are controlled provider tests, not live calls.
- `GMAIL_USE_GEMINI=false` forces Standard classification and automated Gmail handoff extraction even if a key exists for manual uploads. Requested true without a key is now explicitly shown as unavailable/Standard. The UI is read-only and enables no data transfer.
- Existing Gmail restricted-scope/provider-data safeguards remain applicable. See [Gmail policy and setup](gmail-intake.md#google-verification-and-privacy-limitations). Do not enable real restricted-data transfer until disclosure/authorization, provider terms and applicable data-policy requirements are satisfied.

## Unsupported formats and separate assisted-intake phase

| Input | Status |
| --- | --- |
| Digital, scanned, photograph-based and mixed-content **PDF invoices** | Supported by the existing 10 MiB / 20-page / page-pixel checks and bounded PDF/OCR subprocess. Original PDF is retained. |
| Direct JPG / JPEG / PNG files | Not implemented. Save photographs as a readable PDF for the current uploader. Safe direct images need decoding/dimension/pixel limits, canonical conversion, original-image retention and dual original/normalized provenance/hash design. |
| UTF-8 CSV suppliers / purchase orders | Supported, with templates, 256 KiB/500-row limits, preview, existing server validators and atomic commit. CSV opens in Excel/LibreOffice. |
| XLSX | Not implemented. A safe adapter needs ZIP expansion limits, worksheet/cell budgets, formula/external-link/macro rejection and conversion to the same canonical validated preview path. The UI does not pretend to accept XLSX. |
| Supplier documents / Purchase Order PDFs | Investigated; **not implemented** as assisted procurement import. They need a separate typed procurement-source/draft model, private source storage, conservative classification, evidence/uncertainty, editable draft fields, explicit authorized confirmation, and existing procurement validation. They must not be routed into the invoice financial engine as an assisted-import shortcut. |

These optional extensions are a distinct follow-up phase after this essential PS-1 work. No new upload buttons or fake extraction support were added. Supplier approval and PO spending authorization must remain explicit human actions.

## Screenshots

- Collapsed header: [before](images/customer-ps1/before-collapsed.png), [after](images/customer-ps1/after-collapsed.png).
- Native collapsed header: [100%](images/customer-ps1/collapsed-100.png), [125%](images/customer-ps1/collapsed-125.png), [150%](images/customer-ps1/collapsed-150.png), [200%](images/customer-ps1/collapsed-200.png).
- [Supplier onboarding](images/customer-ps1/supplier-onboarding.png), [PO guidance](images/customer-ps1/purchase-order-guidance.png), [actual reading and financial decision](images/customer-ps1/reading-and-financial-decision.png), [archived invoice](images/customer-ps1/archived-invoice.png).
- [Existing-history recovery](images/customer-ps1/safe-sample-recovery.png), [fresh named sample complete](images/customer-ps1/fresh-sample-ready.png).

## Verification and limits

- Full backend regression: **299 passed** (including financial, authorization, Gmail isolation, queue archive, source ambiguity, attempted-provider metadata and additive migration preservation checks).
- Full frontend suite: **83 passed** in 13 files.
- TypeScript, ESLint, Prettier, production build and backend Ruff checks: passed. Alembic model/schema consistency passed with no missing operations; Gitleaks found no source leaks.
- Full real-service Chromium browser suite: **28 passed in one run** (10.8 minutes), including manual procurement/PDF/archive, native zoom/contrast and fresh sample recovery with original email/PDF/history retained.

Tests run against dedicated disposable local databases and scratch document storage. No existing application database, PostgreSQL volume, real credentials, encryption key or original customer history is reset or replaced. No deployment or paid infrastructure activation is performed.

Live Gmail OAuth/refresh/real INBOX attachment intake and live Gemini calls remain outstanding: no real provider credentials or authorized live mailbox were configured here. Browser Gmail/Supabase provider responses are controlled; financial workers, PostgreSQL, stored PDFs, OCR and application services are real. Native Windows execution is not verified in this Linux environment. The production build's existing PDF viewer chunk-size warning remains informational.

### Outstanding live checks

- Register/confirm a real Supabase test account, sign in, create an empty workspace and verify a second real account is denied access. Signed-JWT and controlled UI tests here do not replace that live check.
- With an explicitly authorized test mailbox, verify read-only Gmail consent, actual token refresh/revocation and a real INBOX PDF handoff through the worker. Confirm the original workspace, mailbox checkpoint and immutable records remain scoped correctly.
- Only after provider/data-policy safeguards and informed authorization are in place, test a live Gemini extraction with source quotes and actual model metadata. Check AUTO fallback and strict GEMINI failure behavior without accepting unsupported financial values. Do not send restricted real customer mailbox data merely to run a smoke test.
- Execute the Windows upgrade/readiness/OCR steps on the actual Windows installation. No Windows runtime success is claimed from Linux verification.

See [exact Windows upgrade instructions](windows-ps1-upgrade.md).


## Changed files

- Navigation/recovery: `frontend/src/workspaces.tsx`, `frontend/src/customer.css`, `frontend/src/main.tsx`, `backend/app/workspaces_api.py`.
- Queue visibility: `backend/app/models.py`, `backend/migrations/versions/0011_invoice_queue_visibility.py`, `backend/app/workflow_api.py`, `frontend/src/InvoiceWorkflow.tsx`, `frontend/src/models.ts`.
- Evidence/provider truth: `backend/app/extraction/sourcefacts.py`, `backend/app/extraction/pipeline.py`, `frontend/src/RunDetails.tsx`.
- Procurement guidance: `frontend/src/POEditor.tsx`, `frontend/src/ProcurementImport.tsx`, `frontend/src/pages/Vendors.tsx`.
- Gmail configuration disclosure: `backend/app/email_intake/api.py`, `frontend/src/pages/EmailIntake.tsx`.
- Regression coverage: `backend/tests/application/test_queue_organization.py`, `backend/tests/application/test_ps1_source_pipeline.py`, `backend/tests/browser_sample_recovery_fixture.py`, `frontend/src/workspaces.test.tsx`, `frontend/src/RunDetails.test.tsx`, `frontend/e2e/zzzz-workspace-creation.spec.ts`, `frontend/e2e/zzzzz-customer-ps1.spec.ts`.
- Documentation/evidence: `README.md`, this audit, `docs/windows-ps1-upgrade.md` and `docs/images/customer-ps1/`.
