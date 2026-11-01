# Synthetic-v2 dataset

All entities, tax identifiers, procurement records and invoices are synthetic. No document is payable, and no real bank account or personal data is included. This corpus tests behavior; it does not establish real-world extraction generalization.

## Frozen inventory

- 18 vendors: 12 approved, 4 suspended, 2 inactive.
- 36 POs: 22 open, 8 partially billed, 4 closed, 2 cancelled.
- 26 itemized POs and 10 amount-based POs.
- Currencies: USD 9, INR 7, EUR 6, GBP 5, JPY 4, KWD 5.
- Development: 80 scored PDFs, 12 vendors, 24 POs, eight layout families, 50 digital / 30 scanned.
- Held-out: 40 scored PDFs, six vendors, 12 POs, four different layout families, 24 digital / 16 scanned.
- Eight additional unscored baseline PDFs, one for each partially billed PO.
- Exact-byte replays remain submission cases but are deduplicated for headline extraction metrics: 78 unique development payloads and 39 held-out payloads.

`manifest.json` contains input paths, SHA-256 hashes, split/family/group/order, scan parameters, generator version and random seed. `freeze.json` binds catalogue, manifests, scoring policy, answer files and generator source hashes. Existing samples/ assets and the three-vendor/four-PO legacy seed are unchanged. The first three vendors/four POs in this catalogue retain their original identities; the remaining records exist only in new evaluation databases.

## Inputs and independent answers

- `procurement.json`: reference data, not a mapping from filenames to expected matches.
- `development/inputs/`: development documents; `development/answers.json`: development labels.
- `evaluation-inputs/`: held-out PDFs; answers are separately under repository `evaluation/synthetic-v2/oracle.json`.
- `baseline/`: supported-layout synthetic historical invoices. The runner processes all eight through the real worker before scoring and checks their commitments. No fake OCR events or direct consumption totals are inserted.

Do not feed oracle files, case categories, expected matches or decisions into the application. Input-only child processes receive a PDF, isolated database/storage configuration and an output path. They do not import or load answer files. Normal regression tests inspect held-out public hashes/layout metadata but do not load held-out expected answers. `.dockerignore` excludes both dataset and oracle directories from application images. This is logical process/package separation, not an OS security sandbox against a developer with repository access.

## Scenario/state isolation

Each invocation creates its own randomly named `ig_eval_v2_<24 hex>` databases. It migrates and seeds a new template, executes eight baseline invoices and clones that baseline for each independent scenario group. Duplicate and partial sequences share state only inside their group. No supplied database name can be reset, overwritten or dropped; cleanup checks invocation ownership. The regular demo, historical invoices and commitments are never targets.

Development comprises 32 ordinary valid documents, 12 blocking-state/relationship violations, 12 missing/ambiguous cases, 12 duplicate-family submissions, eight partial-sequence documents and four unsupported tax cases. Held-out comprises 12 ordinary valid documents, six blocking cases, six missing/ambiguous cases, eight duplicate-family submissions, six partial-sequence documents and two unsupported tax cases.

All amounts reconcile through independently checked rational arithmetic. Minor digits: USD/INR/EUR/GBP 2, JPY 0, KWD 3. Construction uses Decimal/ROUND_HALF_UP; validation uses Fraction and integer half-up rounding plus hand-worked boundary tests. Rates are synthetic procurement policy choices, not jurisdiction-specific tax advice. Inclusive, exclusive and deliberately unsupported mixed modes are represented. This coverage does not imply every jurisdiction, discount, withholding or credit-note behavior is covered.

## Layouts and scans

D0–D7: labeled flow, two columns, alternate terminology, aligned label/value layouts, continuation pages, compact forms, service-style presentation and item tables/cards.

H0–H3: separate evaluation layout families with top/column totals, paginated item presentation, alternate visual hierarchy and ledger-like presentation. Layout families, vendor records, derivation families and exact hashes do not cross splits. Shared field concepts and the shared renderer implementation remain a source of synthetic bias.

Scans are rendered at deterministic 120/150/180 DPI with seeded rotation, contrast and blur. They are image-only PDFs. Not every scan transformation damages OCR equally. These are synthetic scans, not a distribution of real photocopiers, handwriting or document damage.

## Reproducibility and use

From backend:

- `uv run python -m scripts.validate_dataset_v2` checks public inputs and development oracles.
- Add `--include-heldout` only for explicitly authorized offline validation.
- `uv run python -m scripts.seed_dataset_v2 --report ../evaluation/synthetic-v2/reports/seed-check.json` proves seeding in a disposable database and removes it.
- `uv run python -m scripts.evaluate_dataset_v2 --mode extraction --split development --report ../evaluation/synthetic-v2/reports/extraction-development.json`.
- Modes: `extraction`, `gold`, `worker`; split: `development` or explicitly `heldout`; provider defaults to `fallback`.
- `uv run python -m scripts.report_dataset_v2` builds aggregate reports after all six combinations complete.

The local PostgreSQL role needs CREATE/DROP DATABASE rights. Set EVAL_ADMIN_DATABASE_URL securely when using another test server. The runner uses that server for new evaluator-owned databases only. Never grant the application a general-purpose production administrator credential.

Use `OMP_THREAD_LIMIT=1` and run reference modes sequentially. Each input child is bounded by existing production subprocess timeouts; those limits are not changed. Live Gemini mode explicitly refuses to run without a configured key. A fallback result is not relabeled as Gemini.

The default generator refuses to overwrite a frozen dataset. To revise content, create a new dataset version and preserve the prior manifest/results. Re-rendering is deterministic for fixed source inputs, seeds and pinned PyMuPDF/Pillow versions; ordinary tests verify representative digital and scan byte determinism.

## Evaluation discipline

This set was held out from parser/prompt tuning of the unchanged Phase 2 application, but it has now been evaluated. If any of these cases informs a parser or prompt change, move it to regression coverage and obtain a fresh untouched evaluation set. Repeated scores on the same synthetic corpus do not prove generalization. Independent human annotation and real-invoice evaluation remain outstanding.
