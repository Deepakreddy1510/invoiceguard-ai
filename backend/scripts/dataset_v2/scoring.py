"""Independent scoring policy; no application helpers or financial-engine imports."""

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

NUMBERS = {
    "quantity",
    "unit_price",
    "net",
    "tax_rate",
    "gross",
    "subtotal",
    "discount",
    "charges",
    "tax",
    "total",
}


def equivalent(field, actual, expected):
    if actual is None or expected is None:
        return actual is expected
    if field in NUMBERS:
        try:
            # Canonical normalized decimal contract; no locale guessing.
            if not re.fullmatch(r"-?\d+(?:\.\d+)?", str(actual)):
                return False
            a, b = Decimal(str(actual)), Decimal(str(expected))
            return a.is_finite() and b.is_finite() and a == b
        except InvalidOperation:
            return False
    return " ".join(str(actual).split()).casefold() == " ".join(str(expected).split()).casefold()


def field_scores(answer, extraction, pages):
    expected = answer["facts"]
    actual = (extraction or {}).get("fields", {})
    counts = defaultdict(int)
    details = []
    page_text = {p["page"]: " ".join(p["text"].split()).casefold() for p in pages or []}

    def one(path, key, gold, observed):
        observed = observed if isinstance(observed, dict) else {}
        value = observed.get("value")
        present = value is not None
        if gold is None:
            counts["absent_gold_fields"] += 1
            counts["correct_abstentions"] += int(not present)
            counts["false_populations"] += int(present)
        else:
            counts["present_gold_fields"] += 1
            counts["correct_fields"] += int(equivalent(key, value, gold))
            counts["missing_extractions"] += int(not present)
            counts["wrong_extractions"] += int(present and not equivalent(key, value, gold))
        if present:
            counts["populated_fields"] += 1
            quote = " ".join((observed.get("quote") or "").split()).casefold()
            evidence = bool(
                quote
                and quote in page_text.get(observed.get("page"), "")
                and gold is not None
                and equivalent(key, value, gold)
            )
            counts["unsupported_extractions"] += int(not evidence)
            counts["backend_unverified_fields"] += int(not observed.get("verified", False))
        details.append(
            {
                "field": path,
                "expected": gold,
                "actual": value,
                "correct": equivalent(key, value, gold),
            }
        )

    for key, gold in expected["fields"].items():
        one(key, key, gold, actual.get(key))
    actual_items = actual.get("items", [])
    used = set()
    for index, item in enumerate(expected["items"]):
        match = next(
            (
                (j, row)
                for j, row in enumerate(actual_items)
                if j not in used
                and isinstance(row.get("sku"), dict)
                and equivalent("sku", row["sku"].get("value"), item["sku"])
            ),
            None,
        )
        counts["expected_line_items"] += 1
        if match:
            used.add(match[0])
            row = match[1]
            counts["matched_line_items"] += 1
        else:
            row = {}
        for key, value in item.items():
            one(f"items/{index}/{key}", key, value, row.get(key))
    counts["extra_line_items"] += len(actual_items) - len(used)
    counts["document_type_checks"] += 1
    counts["correct_document_types"] += int(
        actual.get("document_type") == expected["document_type"]
    )
    return dict(counts), details


def aggregate(results, mode, provider, split):
    counters = defaultdict(int)
    confusion = defaultdict(int)
    breakdowns = {}
    seen = set()
    for r in results:
        counters["attempted_submissions"] += 1
        failed = bool(r.get("technical_failure"))
        counters["technical_failures"] += int(failed)
        if r["sha256"] not in seen:
            seen.add(r["sha256"])
            for k, v in r.get("field_counts", {}).items():
                counters[k] += v
        if mode != "extraction":
            actual = r.get("actual_decision")
            gold = r["expected_decision"]
            counters["decision_checks"] += 1
            counters["correct_decisions"] += int(actual == gold)
            counters["reviews"] += int(actual == "NEEDS_REVIEW")
            counters["unsafe_validations"] += int(actual == "VALIDATED" and gold != "VALIDATED")
            counters["missed_validations"] += int(gold == "VALIDATED" and actual != "VALIDATED")
            confusion[gold + " -> " + str(actual or "TECHNICAL_FAILURE")] += 1
            for key in [
                "vendor",
                "po",
                "commitment",
                "allocations",
                "balance_before",
                "balance_after",
                "replay",
            ]:
                counters[key + "_checks"] += 1
                counters[key + "_correct"] += int(r.get(key + "_correct", False))
            counters["rule_checks"] += r.get("rule_checks", 0)
            counters["correct_rules"] += r.get("correct_rules", 0)
        for key in ["layout", "scanned", "currency", "scenario"]:
            label = key + "=" + str(r[key])
            bucket = breakdowns.setdefault(
                label,
                {
                    "attempted": 0,
                    "technical_failures": 0,
                    "decisions_correct": 0,
                    "present_gold_fields": 0,
                    "correct_fields": 0,
                },
            )
            bucket["attempted"] += 1
            bucket["technical_failures"] += int(failed)
            bucket["decisions_correct"] += int(
                r.get("actual_decision") == r.get("expected_decision") and mode != "extraction"
            )
            bucket["present_gold_fields"] += r.get("field_counts", {}).get("present_gold_fields", 0)
            bucket["correct_fields"] += r.get("field_counts", {}).get("correct_fields", 0)

    def ratio(n, d):
        return {"numerator": counters[n], "denominator": counters[d]}

    return {
        "mode": mode,
        "provider": provider,
        "split": split,
        "unique_pdf_payloads": len(seen),
        "counts": dict(counters),
        "field_correctness": ratio("correct_fields", "present_gold_fields"),
        "unsupported_extraction_rate": ratio("unsupported_extractions", "populated_fields"),
        "decision_correctness": ratio("correct_decisions", "decision_checks")
        if mode != "extraction"
        else None,
        "review_rate": ratio("reviews", "attempted_submissions") if mode != "extraction" else None,
        "confusion_matrix": dict(confusion),
        "breakdowns": breakdowns,
        "cases": results,
    }
