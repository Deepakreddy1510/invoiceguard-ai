# Final product pass — verification record

The final code is published only after its relevant local checks pass. GitHub Actions runs again on the published commit; use the commit's integrated-check result for its final hosted CI conclusion. No deployment is performed.

## Phase results

1. Correctness: full PO identifiers retained, false email conflicts fixed, exact case/separator distinctions preserved, conservative Gemini evidence guard added. The email financial policy and financial engine are unchanged. Nineteen new reference/policy regressions reproduce the former defect and guard conflict/email-only behaviour.
2. Shared UX: business labels, ordered issues, grouped recorded checks, decision-first presentation, field evidence, structured email provenance, actual invoice/PO comparison and ADMIN-only collapsed technical disclosures.
3. Screens: Overview attention entry points and disclosed operational metrics; Processing decision/why/next action and genuine six-stage views; Email Intake actionable/all filters, selected attachment activity and separate processing/financial states; Exception review grouped reasons with existing correction/version/attestation controls; Activity History server-side filtering, invoice context, actor labels, original records retained. Existing vendor/PO CRUD/import and routes are preserved.
4. Data: separate versioned Asterfield workspace, 18 vendors, 36 POs, 21 PDFs, real worker decisions and commitments, safe repeat installation, verified preference only after success. Details and Windows upgrade precautions are in [the product guide](product-refinement.md).
5. Verification: results below, current source secret scan, migration drift check, production image build and recorded deterministic data integrity. Windows and credentialed external-provider tests remain manual.

## Commands and actual results

Commands below are run from `backend` or `frontend` as indicated. The cloud test database uses host port 5432; **the user's Windows demo stays on port 5434**. Tests use dedicated/disposable databases, not the user's demonstration volume.

| Check | Command actually executed | Result |
| --- | --- | --- |
| Backend full suite | `TEST_DATABASE_URL=.../invoiceguard_gmail_test .venv/bin/pytest -q` | **232 passed, 0 failed**, one upstream Starlette/httpx deprecation warning |
| Final sample-data change | `.venv/bin/pytest tests/application/test_asterfield.py -q` | **23 passed, 0 failed** after the final PDF layout/polling refinement |
| Backend lint | `.venv/bin/ruff check app tests migrations scripts` | Passed |
| Backend formatting | `.venv/bin/ruff format --check app tests migrations scripts` | Passed, 103 files |
| Migration drift | `DATABASE_URL=.../invoiceguard_gmail_test .venv/bin/alembic check` | No new upgrade operations detected |
| Frontend tests | `npm test` | **32 passed, 0 failed** |
| TypeScript | `npm run typecheck` | Passed |
| Frontend lint | `npm run lint` | Passed, zero permitted warnings |
| Frontend formatting | `npm run format:check` | Passed |
| Production frontend | `npm run build` | Passed |
| Real-service browser | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m scripts.browser_regression` | **13 passed, 0 failed, 0 skipped** |
| Frozen dataset | `.venv/bin/python -m scripts.validate_dataset_v2` | 128/128 PDF hashes; 80/80 development oracles; original 80 development + 40 held-out + 8 baseline PDFs preserved |
| Add-only installer | `PYTHONPATH=. .venv/bin/python /tmp/verify-asterfield.py` (session-only harness) | Migrated owned database, ran installer twice, compared reports; 21/21 decisions agreed with independent expected outcomes and all 36 PO consuming balances matched |
| Source secrets | `gitleaks dir <public-source-copy> --redact --no-banner` | No leaks; ignored private files excluded from publication |
| Production image | `docker build --secret id=ca_bundle,src=/etc/ssl/certs/ca-certificates.crt -t invoiceguard-ai:product-refinement .` | Passed with TLS verification enabled; BuildKit's existing AUTH_MODE-name warning is not a credential finding |

The session-only installer harness uses `DatabasePool` to create/migrate/drop only owned `ig_eval_v2_*` databases, masks provider credentials, and runs `scripts.install_asterfield_demo` twice. The repository's automated `test_actual_worker_decisions_balances_reinstallation_and_legacy_preservation` additionally seeds and checks legacy procurement, row counts, run IDs and commitments across reinstallation. The local browser harness starts actual FastAPI, worker and Vite against an owned database and removes only those test resources afterward.

Browser coverage includes new uploads, real PDF/OCR, immutable decisions, financial explanations, cumulative partial billing, business duplicates, exact replay, missing information, source preview, correction/revalidation, Gmail provider-mocked handoff, current-vs-original run history, workspace isolation, polling/manual selection, Asterfield installation/replay, keyboard navigation, WCAG A/AA scans, and 1440/1024/390-pixel layouts. These are functional browser tests, not a static mockup. Initial runs caught stale copy assertions and a genuine definition-list accessibility defect; all were corrected before the reported final pass. No test was skipped or weakened to conceal a business failure.

## Financial and data integrity

- `backend/app/validation/engine.py` SHA-256 is unchanged: `f61250c319ad33e4457d6f4ffbcdaf35b5dbc9160a48b5728751408c05337072`.
- No schema/model/migration change. Existing upgrade-preservation and security tests remain included in the full suite.
- No production worker/extraction/financial rule changes; only email candidate recognition and read-only operational views changed in backend application code.
- Original workspace IDs, records, artifacts and financial commitments are preserved. No demo reset, volume removal, historical reservation edits, held-out-answer changes or deployment.
- The new data reports **14 validated / 21 submitted**, **6 blocked / 21**, **1 review / 21**, with **21/21 expected decisions matched**. This is scripted sample-workflow correctness, not extraction benchmark accuracy or a real-world generalization claim.
- Real OCR observed on the scanned and photographed samples. Installer uses FALLBACK even if a local Gemini key exists. The tax-inclusive case verifies extraction of its tax basis; balances use Decimal half-up rounding for the four represented two-minor-digit currencies.
- [Actual sample execution report](asterfield-execution.json) contains synthetic run identifiers, per-document providers/OCR pages and verified PO balances from a disposable verification database. These identifiers describe that execution; they are not IDs in the user's Windows database. The source hashes identify the tested pre-commit source; the base commit is explicitly labelled.

## Known limitations

No credentialed Gmail message delivery, live Gemini call, hosted OIDC login, S3/Render provisioning, Windows execution or public HTTPS deployment was performed. Real provider verification must happen with the user's own configured credentials. English synthetic layouts are intentionally readable; the photographed sample is a generated raster derivative. Three layout families are presentation fixtures, not independently held-out real supplier documents. Existing payment, settlement, allocation and tax-policy limitations remain documented. Desktop and narrow-window automated checks passed; a final Windows visual review with the user's fonts/OCR installation remains appropriate before recording.

The existing CI workflow and all its validation steps remain intact, including uv post-job cleanup and process-group termination. The final response links the actual CI run and conclusion after publication; no pending run is described as green.

## Exact changed files

- `README.md`
- `backend/app/email_intake/api.py`
- `backend/app/email_intake/screening.py`
- `backend/app/operations_api.py`
- `backend/demo/asterfield-v1/01-office-supplies.pdf`
- `backend/demo/asterfield-v1/02-it-support-october.pdf`
- `backend/demo/asterfield-v1/03-it-support-november.pdf`
- `backend/demo/asterfield-v1/04-it-support-over-budget.pdf`
- `backend/demo/asterfield-v1/05-chairs-digital.pdf`
- `backend/demo/asterfield-v1/06-cleaning-scan.pdf`
- `backend/demo/asterfield-v1/07-packaging-photo.pdf`
- `backend/demo/asterfield-v1/08-printing.pdf`
- `backend/demo/asterfield-v1/09-delivery-service.pdf`
- `backend/demo/asterfield-v1/10-safety-kits.pdf`
- `backend/demo/asterfield-v1/11-catering-missing-reference.pdf`
- `backend/demo/asterfield-v1/12-electrical.pdf`
- `backend/demo/asterfield-v1/13-training-tax-exempt.pdf`
- `backend/demo/asterfield-v1/14-scanners-usd.pdf`
- `backend/demo/asterfield-v1/15-uniforms-eur.pdf`
- `backend/demo/asterfield-v1/16-analytics-gbp.pdf`
- `backend/demo/asterfield-v1/17-suspended-supplier.pdf`
- `backend/demo/asterfield-v1/18-inactive-supplier.pdf`
- `backend/demo/asterfield-v1/19-closed-order.pdf`
- `backend/demo/asterfield-v1/20-office-supplies-copy.pdf`
- `backend/demo/asterfield-v1/21-supplier-order-mismatch.pdf`
- `backend/demo/asterfield-v1/manifest.json`
- `backend/demo/asterfield-v1/procurement.json`
- `backend/scripts/install_asterfield_demo.py`
- `backend/tests/application/test_asterfield.py`
- `backend/tests/application/test_gmail.py`
- `backend/tests/application/test_product_refinement.py`
- `docs/asterfield-demo-guide.md`
- `docs/asterfield-execution.json`
- `docs/product-refinement-verification.md`
- `docs/product-refinement.md`
- `frontend/e2e/complete.spec.ts`
- `frontend/e2e/email.spec.ts`
- `frontend/e2e/product.spec.ts`
- `frontend/e2e/redesign.spec.ts`
- `frontend/e2e/workflow.spec.ts`
- `frontend/e2e/zz-asterfield.spec.ts`
- `frontend/src/App.tsx`
- `frontend/src/EmailIntake.test.tsx`
- `frontend/src/InvoiceWorkflow.test.tsx`
- `frontend/src/InvoiceWorkflow.tsx`
- `frontend/src/POComparison.tsx`
- `frontend/src/RunDetails.test.tsx`
- `frontend/src/RunDetails.tsx`
- `frontend/src/TechnicalDetails.tsx`
- `frontend/src/business.test.tsx`
- `frontend/src/business.ts`
- `frontend/src/pages/Audit.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/EmailIntake.tsx`
- `frontend/src/pages/Reviews.tsx`
- `frontend/src/styles.css`
- `frontend/src/ui.tsx`
- `frontend/src/workspaces.tsx`
