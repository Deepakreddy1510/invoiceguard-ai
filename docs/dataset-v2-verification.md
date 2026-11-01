# Synthetic-v2 implementation and verification

Implemented only dataset generation, independent oracles, evaluation infrastructure and tests. No production processing/financial rules, legacy seeds, migrations or regression fixtures were changed. Nothing was committed, deployed or published.

## Inventory and distributions

- 18 vendors: 12 APPROVED, 4 SUSPENDED, 2 INACTIVE.
- 36 POs: 22 OPEN, 8 PARTIALLY_BILLED, 4 CLOSED, 2 CANCELLED.
- 26 ITEMIZED, 10 AMOUNT_BASED POs.
- Currency PO counts: USD 9, INR 7, EUR 6, GBP 5, JPY 4, KWD 5.
- 80 development PDFs: 50 digital, 30 scanned; 12 vendors and 24 POs; eight development layout families.
- 40 held-out PDFs: 24 digital, 16 scanned; six different vendors and 12 POs; four different evaluation layout families.
- Eight additional unscored baseline invoices are processed by the actual worker to establish prior consumption. Total PDFs: 128, of which 120 are scored submissions.
- Exact-byte repeats are intentional: 78 unique development payloads and 39 unique held-out payloads, 117 unique scored payloads total.
- Layout counts: D0 10, D1 10, D2 10, D3 10, D4 9, D5 9, D6 11, D7 11; H0 11, H1 11, H2 9, H3 9.
- Tax-mode counts: development 61 exclusive, 15 inclusive, 4 unsupported mixed; held-out 31 exclusive, 7 inclusive, 2 unsupported mixed. Five development and three held-out documents have multiple items with differing line rates.

All names, identifiers and invoice details are synthetic. Tax rates and tolerances represent declared prototype policy, not real jurisdictional legal compliance. Scans use seeded DPI, rotation, contrast and blur; they are not samples of real scanner populations. Fractional monetary values are represented; comprehensive fractional-quantity, credit-note and jurisdictional-tax coverage is not claimed.

## Integrity and oracle validation

Executed `uv run python -m scripts.validate_dataset_v2 --include-heldout`:

- All 128 hashes, PDF readability/page limits, split counts, vendor/PO references and catalogue gross arithmetic passed.
- 80 development and 40 held-out oracle records passed independent rational arithmetic and balance-delta checks.
- Digital source renderings were checked against expected visible values. Scans derive from the same renderer; no independent human image annotation was performed.
- No exact hash, derivation family or layout family crosses splits; procurement vendors and POs are partitioned.
- The ordinary test suite does not load held-out expected answers. Application code and input child processes do not import oracle assets. Build exclusions keep datasets and evaluation labels out of application images.
- The independent scorer does not import the production comparison helper. Wrong values, missing values, false populations and unsupported evidence/value claims are separate counters.
- Tests cover hand-worked half-up boundaries for USD, INR, EUR, GBP, JPY and KWD. Digits are 2/2/2/2/0/3 respectively. Construction uses Decimal while independent validation uses Fraction/integer rounding.

The oracle models explicitly annotated matching, required-field, state, currency, duplicate, capacity and quantity controls. Financial arithmetic is independently checked. This is not an exhaustive legal or financial-policy oracle for every possible invoice.

## Actual reference results

All six mode/split combinations were executed sequentially with OMP_THREAD_LIMIT=1. No production timeouts were changed.

| Mode | Split | Present fields correct | Strict decisions correct | Reviews | Technical failures | Unsafe validations |
|---|---|---:|---:|---:|---:|---:|
| PDF extraction / fallback | Development | 848/1616 | N/A | N/A | 0 | N/A |
| PDF extraction / fallback | Held-out | 340/815 | N/A | N/A | 0 | N/A |
| Gold fields / financial engine | Development | Gold supplied | 79/80 | 19/80 | 0 | 0 |
| Gold fields / financial engine | Held-out | Gold supplied | 38/40 | 12/40 | 0 | 0 |
| PDF / real worker / database | Development | 848/1616 | 40/80 | 52/80 | 0 | 0 |
| PDF / real worker / database | Held-out | 340/815 | 14/40 | 36/40 | 0 | 0 |

These scores show limited automatic extraction coverage on varied formats. They are not presented as evidence of successful real-world generalization. Review on a gold-valid invoice is counted as missed validation, not a successful decision. Matching/financial gaps remain visible rather than changing expected answers to agree with the application.

Fallback field details, deduplicated by exact bytes:

| Metric | Development | Held-out |
|---|---:|---:|
| Unsupported populated fields | 62/910 | 1/341 |
| Wrong non-null extractions | 60 | 1 |
| Missing present gold fields | 708 | 474 |
| Correct abstentions on absent fields | 12/14 | 7/7 |
| Matched line items | 22/88 | 14/45 |

The full worker mode actually ran production ingestion and the Python worker. It exercised 120 scored submissions across isolated groups, including 117 unique scored payloads and three exact-byte replays. Each split also executed eight baseline invoices through the worker. Decisions, rule results, event counts, new commitments, quantity allocations, replays and remaining balances were read from PostgreSQL and compared with the oracle.

Worker-mode commitment deltas matched gold in 48/80 development and 22/40 held-out submissions. Final balances matched in 42/80 and 16/40 respectively. These mismatches largely reflect missed automation and the subsequent state of partial sequences, not technical database failures. Gold-mode commitment and final-balance correctness was 79/80 and 40/40. Per-case differences are retained in the JSON reports.

Live Gemini: **UNRUN**. No key is configured. The runner refuses an explicitly requested Gemini evaluation without a key; fallback is never presented as a successful Gemini extraction. No Gemini accuracy/generalization figure is claimed.

## Regression results and initial resource failure

- Final backend suite: **89 passed, 0 failed** (58 original tests plus 31 dataset infrastructure tests).
- Frontend: **4 passed, 0 failed**; TypeScript/Vite production build passed.
- Original Playwright suite: **6 passed, 0 failed**, using isolated legacy seed data, separate API/worker/frontend ports and a disposable database. The running demo was not used for browser test submissions.
- Ruff lint and format checks passed.
- Existing Starlette TestClient/httpx deprecation warning remains unsuppressed.

An initial concurrent run produced one worker development technical failure and one original scanned-PDF regression timeout while multiple OCR workloads were active. Those original evaluation reports remain under `reports/initial-concurrent/`. The reference workload was rerun sequentially with one OCR thread; the affected extraction suite and full regression then passed. Parser, prompts, production rules and timeout values were not changed. Do not infer stress-load reliability from the controlled reference run.

## Confirmed matching defect — not fixed

The production engine combines vendor-code, tax-ID and name matches using OR. When two vendors share a normalized name, it can fail to resolve a unique vendor even when code and tax ID identify one unambiguously.

Reproduced cases:

- Development `b46a1c2fa1ec773c`: expected VALIDATED, actual NEEDS_REVIEW for an approved vendor.
- Held-out `5a60807cba1fc09a`: expected BLOCKED, actual NEEDS_REVIEW for a suspended vendor.
- Held-out `755b225b9b6ed81f`: expected BLOCKED, actual NEEDS_REVIEW for an inactive vendor.

A cancelled PO case also has incorrect vendor resolution but retains the correct BLOCKED final outcome through its PO rule. This illustrates why matching and rule correctness are reported separately from final decisions.

Reproduce from backend:

```sh
uv run python -m scripts.reproduce_dataset_v2_gap \
  --case b46a1c2fa1ec773c --split development \
  --report ../evaluation/synthetic-v2/reports/gap-ambiguous-approved-vendor.json
```

The reproduction deliberately exits **2** on the mismatch, writes the observed results and removes its database. This is an unresolved business-rule discrepancy, not a passing regression assertion. It was not hidden with an xfail or resolved by changing the oracle. A policy/production-code correction requires separate approval.

## Isolation and preservation

The six reference combinations created and removed **306 evaluator-owned databases**. The standalone seed check independently created 18 vendors, 36 POs and eight worker-created baseline commitments, then removed its database. Focused gap reproductions and test databases were also removed.

Read-only before/after fingerprints show:

- All 13 demo tables unchanged, including their row contents.
- Demo remains at 10 documents and 5 commitments.
- All 40 protected production/migration/legacy assets unchanged.
- No `ig_eval_v2_...` databases remained at the preservation check.

Evidence: `evaluation/synthetic-v2/reports/preservation.json`.

Database names are generated internally and checked against a strict format. Drop operations require in-memory invocation ownership. Existing targets are never reset or overwritten. Each scenario group starts from the worker-established baseline; duplicate/partial sequences share only their own cloned state. Repeated evaluation cannot consume the demo's PO balances.

## Reproducibility and commands

Dataset version: synthetic-v2.0.0. Seed: 20261101. Source/PDF hashes and pinned renderer versions are recorded in freeze.json. Reports contain application source hashes, Git HEAD plus dirty state, evaluator source hashes, oracle/scoring hashes, Python/PyMuPDF/Tesseract versions, runtime date and OCR thread limit. The application is currently uncommitted, so Git HEAD alone is not a sufficient implementation identifier.

Executed commands included generation, explicit public/private integrity validation, all three evaluation modes on both splits, report summarization, standalone seeding, focused failing-case reproduction, full Pytest, Vitest/build, isolated Playwright, Ruff and preservation checks.

The renderer determinism test passes for representative digital/scanned inputs. Full cross-platform byte-identical regeneration across different library/font versions is not claimed. The frozen generator refuses overwrite; content changes require a new dataset version. Runtime business date is recorded rather than modifying the application's clock.

## Files created or changed

Changed existing files: `backend/pyproject.toml`, `backend/uv.lock` (development-only Pillow dependency).

Created:

- `.dockerignore`.
- `backend/scripts/dataset_v2/`: __init__, common, catalogue, facts, oracle, render, generate, integrity, isolation, seed, child, scoring and runner modules.
- `backend/scripts/generate_dataset_v2.py`, `validate_dataset_v2.py`, `evaluate_dataset_v2.py`, `seed_dataset_v2.py`, `report_dataset_v2.py`, `reproduce_dataset_v2_gap.py`.
- `backend/tests/datasets/test_catalog_integrity.py`, `test_oracle_consistency.py`, `test_split_integrity.py`, `test_evaluation_isolation.py`, `test_evaluator_metrics.py`.
- `datasets/synthetic-v2/`: catalogue, manifest, freeze file, README, 80 development inputs and labels, 40 held-out inputs, eight baseline PDFs.
- `evaluation/synthetic-v2/`: held-out oracle, scoring policy, README, per-mode reports, initial concurrent observations, summary, seed/preservation checks and focused gap reports.
- This verification document. A machine-readable exact file inventory is under evaluation/synthetic-v2/reports/file-inventory.json.

Ignored `.local/dataset-v2` files contain diagnostic logs, fingerprints and the isolated browser harness; they are not application code.

## Limitations

- Synthetic, developer-authored data with shared rendering code is not an independently collected real-invoice benchmark. Gold labels have not had independent human review.
- Held-out means not used for parser/prompt tuning during this evaluation. The set has now been scored; cases that inform future tuning must move to regression and be replaced for fresh held-out claims.
- Answer isolation is process-input/package separation, not a filesystem security sandbox against a developer with repository access.
- Evidence scoring checks source quote existence and gold value agreement; it does not replace semantic/bounding-box adjudication.
- The matching defect is unresolved, and the fallback's high review rate remains a material limitation.
- Complex tax compliance, broad locale parsing, handwriting and extensive fractional-quantity coverage remain untested by this corpus.
- No live Gemini, hosting, publication or unrelated Phase 3 implementation was performed.
