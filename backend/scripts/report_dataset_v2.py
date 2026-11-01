"""Offline report summarizer; not collected by ordinary regression tests."""

from collections import Counter

from scripts.dataset_v2.common import DATA, PRIVATE, load, source_hashes, write_json


def summarize():
    cat = load(DATA / "procurement.json")
    manifest = load(DATA / "manifest.json")
    reports = []
    for mode in ["extraction", "gold", "worker"]:
        for split in ["development", "heldout"]:
            report = load(PRIVATE / f"reports/{mode}-{split}.json")
            assert report["isolation"]["databases_remaining"] == 0
            assert report["provenance"]["application_sources"] == source_hashes()
            reports.append(report)
    summary = {
        "dataset": {
            "vendors": len(cat["vendors"]),
            "purchase_orders": len(cat["purchase_orders"]),
            "scored_pdfs": len(manifest["documents"]),
            "baseline_pdfs": len(manifest["baseline"]),
            "vendor_statuses": dict(Counter(v["status"] for v in cat["vendors"])),
            "po_statuses": dict(Counter(p["status"] for p in cat["purchase_orders"])),
            "currencies": dict(Counter(p["currency"] for p in cat["purchase_orders"])),
            "billing_modes": dict(Counter(p["billing_mode"] for p in cat["purchase_orders"])),
            "layout_counts": dict(Counter(d["layout"] for d in manifest["documents"])),
            "scanning": {
                "digital": sum(not d["scanned"] for d in manifest["documents"]),
                "scanned": sum(d["scanned"] for d in manifest["documents"]),
            },
        },
        "evaluations": [
            {
                k: r[k]
                for k in [
                    "mode",
                    "split",
                    "provider",
                    "counts",
                    "field_correctness",
                    "decision_correctness",
                    "review_rate",
                    "unique_pdf_payloads",
                ]
            }
            for r in reports
        ],
        "reference_databases_created_and_removed": sum(
            r["isolation"]["databases_created"] for r in reports
        ),
        "gemini": load(PRIVATE / "reports/live-gemini.json"),
        "limitations": [
            "Synthetic, developer-authored corpus; no independently blinded human annotation or real-invoice benchmark.",
            "Held-out inputs have now been scored; they must not be used for parser or prompt tuning while retaining held-out claims.",
            "Gold results isolate financial matching from extraction; gold evidence is deliberately assumed rather than extracted.",
            "Quote evidence checks are automatic; no manual bounding-box adjudication was performed.",
            "Initial concurrent observations are retained separately; reference runs are sequential with OMP_THREAD_LIMIT=1.",
            "Runtime business date is recorded; current source invoices have fixed 2026 dates.",
            "No claim of live Gemini extraction or real-world generalization.",
        ],
    }
    write_json(PRIVATE / "reports/summary.json", summary)
    lines = [
        "# Synthetic-v2 measured evaluation",
        "",
        "| Mode | Split | Present fields correct | Decisions correct | Reviews | Technical failures | Unsafe validations |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in reports:
        counts = r["counts"]
        f = r["field_correctness"]
        d = r["decision_correctness"]
        review = r["review_rate"]

        def ratio(x):
            return f"{x['numerator']}/{x['denominator']}" if x else "Not applicable"

        field = ratio(f) if r["mode"] != "gold" else "Gold supplied"
        lines.append(
            f"| {r['mode']} | {r['split']} | {field} | {ratio(d)} | {ratio(review)} | {counts['technical_failures']} | {counts.get('unsafe_validations', 'Not applicable')} |"
        )
    lines += [
        "",
        "Field denominators exclude exact-byte replays. Decision and review denominators include every submission, including replays. Wrong, missing and unsupported fields are reported separately in JSON. Per-layout breakdowns count submissions, so replay weighting can differ from deduplicated headline field metrics.",
        "",
        "Gold decision mismatches:",
    ]
    for r in reports:
        if r["mode"] == "gold":
            for case in r["cases"]:
                if case.get("actual_decision") != case["expected_decision"]:
                    lines.append(
                        f"- {r['split']} `{case['id']}`: expected {case['expected_decision']}, actual {case.get('actual_decision')}; {case.get('rule_mismatches')}"
                    )
    lines += ["", "## Limits", *["- " + v for v in summary["limitations"]]]
    (PRIVATE / "reports/summary.md").write_text("\n".join(lines) + "\n")
    return summary


if __name__ == "__main__":
    data = summarize()
    print(
        {
            "scored_pdfs": data["dataset"]["scored_pdfs"],
            "reference_databases_created_and_removed": data[
                "reference_databases_created_and_removed"
            ],
            "gemini": data["gemini"]["status"],
        }
    )
