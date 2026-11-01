# Offline synthetic-v2 oracle and reports

`oracle.json` contains held-out expected fields, matching, rule outcomes, decisions, allocation/commitment deltas and balances. It is not an application input. `scoring-policy.json` defines canonical decimal/string comparison, separate present/missing denominators, unsafe validations and technical failures.

Oracles are developer-authored from declared source facts and an independent rational-arithmetic policy model. They are not produced by asking the application to approve its own outputs. They are machine-validated, not independently human-adjudicated annotations. Deliberate unsupported tax cases check net/tax/gross sums without pretending to infer a legal tax formula.

Three modes:

1. `extraction`: actual PDF/OCR/field pipeline in an input-only process; offline comparison with gold labels.
2. `gold`: assumed verified gold facts supplied to the unchanged production finalization engine; this isolates financial matching/controls from extraction. It is not evidence that a PDF was parsed successfully.
3. `worker`: actual ingestion and Python worker in disposable PostgreSQL databases; persist and score run events, decisions, matching, commitments, quantities, replay and remaining balances.

Reports contain attempted/unique counts, exact numerators/denominators, false populations, unsupported evidence/value claims, wrong/missing fields, matched/extra items, rule and decision correctness, confusion matrices, review rates, unsafe validations, commitment/allocation/balance correctness, technical failures and per-case mismatches. Application source hashes, Git HEAD plus dirty status, dataset/oracle/policy hashes, provider/runtime versions, OCR thread limit and runtime date are recorded. Git HEAD alone does not identify the current uncommitted implementation.

Reference runs are sequential with OMP_THREAD_LIMIT=1. Initial concurrent observations are preserved under `reports/initial-concurrent/`, including any technical failures. They are not silently discarded. All reported reference modes use fallback; `live-gemini.json` explicitly records UNRUN without credentials.

Headline extraction metrics deduplicate exact bytes. Decision/review metrics count submissions. Breakdown field counts are submission-weighted, so they can differ from headline denominators. A review of a gold-valid invoice is missed automation, not a correct validation. Technical failures remain in attempted denominators. Unsupported counts use gold agreement and quote existence; this is not a full manual semantic/bounding-box review.

Known financial mismatch reproduction is opt-in via `scripts.reproduce_dataset_v2_gap`; it intentionally exits 2 when actual and independently expected outcomes differ. Those reports are not converted into passing tests or used to change production rules.
