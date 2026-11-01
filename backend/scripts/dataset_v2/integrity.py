"""Dataset/oracle checks; private held-out labels load only with explicit opt-in."""

from collections import Counter
from fractions import Fraction

import pymupdf

from scripts.dataset_v2.common import DATA, PRIVATE, digest, load
from scripts.dataset_v2.oracle import rounded, validate_financial_facts


def validate_catalogue(cat):
    assert len(cat["vendors"]) == 18 and len(cat["purchase_orders"]) == 36
    assert Counter(v["status"] for v in cat["vendors"]) == {
        "APPROVED": 12,
        "SUSPENDED": 4,
        "INACTIVE": 2,
    }
    assert Counter(p["status"] for p in cat["purchase_orders"]) == {
        "OPEN": 22,
        "PARTIALLY_BILLED": 8,
        "CLOSED": 4,
        "CANCELLED": 2,
    }
    vendor_ids = {v["id"] for v in cat["vendors"]}
    assert len(vendor_ids) == 18
    assert len({p["id"] for p in cat["purchase_orders"]}) == 36
    assert len({p["number"] for p in cat["purchase_orders"]}) == 36
    for p in cat["purchase_orders"]:
        assert p["vendor_id"] in vendor_ids and p["issued_on"] <= p["valid_until"]
        gross = Fraction(0)
        for item in p["items"]:
            n = rounded(Fraction(item["quantity"]) * Fraction(item["unit_price"]), p["currency"])
            gross += n + rounded(n * Fraction(item["tax_rate"]), p["currency"])
        assert gross == Fraction(p["authorized_gross"]), (p["number"], gross, p["authorized_gross"])
    return True


def validate_public():
    manifest = load(DATA / "manifest.json")
    cat = load(DATA / "procurement.json")
    freeze = load(DATA / "freeze.json")
    validate_catalogue(cat)
    assert digest(DATA / "manifest.json") == freeze["manifest_sha256"]
    assert digest(DATA / "procurement.json") == freeze["catalogue_sha256"]
    docs = manifest["documents"]
    assert len(docs) == 120
    assert Counter(d["split"] for d in docs) == {"development": 80, "heldout": 40}
    assert Counter(d["split"] for d in docs if d["scanned"]) == {"development": 30, "heldout": 16}
    sets = {s: {d["layout"] for d in docs if d["split"] == s} for s in ["development", "heldout"]}
    assert len(sets["development"]) == 8 and len(sets["heldout"]) == 4
    assert sets["development"].isdisjoint(sets["heldout"])
    for key in ["sha256", "derivation_family"]:
        left = {d[key] for d in docs if d["split"] == "development"}
        right = {d[key] for d in docs if d["split"] == "heldout"}
        assert left.isdisjoint(right), f"Cross-split {key} leakage"
    assert Counter(v["split"] for v in cat["vendors"]) == {"development": 12, "heldout": 6}
    assert Counter(p["split"] for p in cat["purchase_orders"]) == {"development": 24, "heldout": 12}
    for d in docs + manifest["baseline"]:
        path = DATA / d["file"]
        assert path.resolve().is_relative_to(DATA.resolve())
        assert digest(path) == d["sha256"]
        with pymupdf.open(path) as pdf:
            assert 1 <= len(pdf) <= 20 and not pdf.needs_pass
    assert len(manifest["baseline"]) == 8
    return {
        "vendors": 18,
        "purchase_orders": 36,
        "development_pdfs": 80,
        "heldout_pdfs": 40,
        "baseline_pdfs": 8,
        "hashes_verified": 128,
        "scan_count": 46,
        "layout_families": 12,
    }


def validate_answers(split):
    manifest = load(DATA / "manifest.json")
    freeze = load(DATA / "freeze.json")
    path = DATA / "development/answers.json" if split == "development" else PRIVATE / "oracle.json"
    assert digest(path) == freeze["answer_sha256"][split]
    answers = load(path)["cases"]
    entries = {d["id"]: d for d in manifest["documents"] if d["split"] == split}
    assert set(answers) == set(entries)
    for cid, answer in answers.items():
        validate_financial_facts(answer["facts"], answer["source_currency"])
        if answer["expected_decision"] != "VALIDATED":
            assert Fraction(answer["commitment_delta"]) == 0
        if answer["balance_before"] is not None:
            assert Fraction(answer["balance_before"]) - Fraction(
                answer["commitment_delta"]
            ) == Fraction(answer["balance_after"])
        assert answer["expected_decision"] in ["VALIDATED", "BLOCKED", "NEEDS_REVIEW"]
        d = entries[cid]
        if not d["scanned"]:
            with pymupdf.open(DATA / d["file"]) as pdf:
                text = " ".join(" ".join(p.get_text().split()) for p in pdf).casefold()
                for value in answer["visible_values"]:
                    assert " ".join(value.split()).casefold() in text, (cid, value)
    return {"split": split, "oracles_checked": len(answers)}
