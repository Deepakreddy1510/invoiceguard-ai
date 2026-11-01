# Synthetic-v2 measured evaluation

| Mode | Split | Present fields correct | Decisions correct | Reviews | Technical failures | Unsafe validations |
|---|---|---:|---:|---:|---:|---:|
| extraction | development | 848/1616 | Not applicable | Not applicable | 0 | Not applicable |
| extraction | heldout | 340/815 | Not applicable | Not applicable | 0 | Not applicable |
| gold | development | Gold supplied | 79/80 | 19/80 | 0 | 0 |
| gold | heldout | Gold supplied | 38/40 | 12/40 | 0 | 0 |
| worker | development | 848/1616 | 40/80 | 52/80 | 0 | 0 |
| worker | heldout | 340/815 | 14/40 | 36/40 | 0 | 0 |

Field denominators exclude exact-byte replays. Decision and review denominators include every submission, including replays. Wrong, missing and unsupported fields are reported separately in JSON. Per-layout breakdowns count submissions, so replay weighting can differ from deduplicated headline field metrics.

Gold decision mismatches:
- development `b46a1c2fa1ec773c`: expected VALIDATED, actual NEEDS_REVIEW; {'VENDOR_APPROVED': {'actual': None, 'expected': 'PASS'}, 'VENDOR_IDENTITY': {'actual': 'REVIEW', 'expected': 'PASS'}, 'VENDOR_PO': {'actual': 'REVIEW', 'expected': 'PASS'}}
- heldout `5a60807cba1fc09a`: expected BLOCKED, actual NEEDS_REVIEW; {'VENDOR_APPROVED': {'actual': None, 'expected': 'BLOCK'}, 'VENDOR_IDENTITY': {'actual': 'REVIEW', 'expected': 'PASS'}, 'VENDOR_PO': {'actual': 'REVIEW', 'expected': 'PASS'}}
- heldout `755b225b9b6ed81f`: expected BLOCKED, actual NEEDS_REVIEW; {'VENDOR_APPROVED': {'actual': None, 'expected': 'BLOCK'}, 'VENDOR_IDENTITY': {'actual': 'REVIEW', 'expected': 'PASS'}, 'VENDOR_PO': {'actual': 'REVIEW', 'expected': 'PASS'}}

## Limits
- Synthetic, developer-authored corpus; no independently blinded human annotation or real-invoice benchmark.
- Held-out inputs have now been scored; they must not be used for parser or prompt tuning while retaining held-out claims.
- Gold results isolate financial matching from extraction; gold evidence is deliberately assumed rather than extracted.
- Quote evidence checks are automatic; no manual bounding-box adjudication was performed.
- Initial concurrent observations are retained separately; reference runs are sequential with OMP_THREAD_LIMIT=1.
- Runtime business date is recorded; current source invoices have fixed 2026 dates.
- No claim of live Gemini extraction or real-world generalization.
