from scripts.dataset_v2.common import DATA, load
from scripts.dataset_v2.facts import make_invoice
from scripts.dataset_v2.render import draw_pdf
from scripts.dataset_v2.scoring import equivalent, field_scores


def test_scorer_separates_wrong_unsupported_and_absent_values():
    answer = {
        "facts": {
            "document_type": "INVOICE",
            "fields": {"total": "10.00", "invoice_number": None},
            "items": [],
        }
    }
    actual = {
        "fields": {
            "document_type": "INVOICE",
            "total": {"value": "11", "page": 1, "quote": "Total: 11", "verified": True},
            "invoice_number": {"value": "FAKE", "page": 1, "quote": "FAKE", "verified": True},
            "items": [],
        }
    }
    counts, _ = field_scores(answer, actual, [{"page": 1, "text": "Total: 11"}])
    assert counts["correct_fields"] == 0 and counts["wrong_extractions"] == 1
    assert counts["unsupported_extractions"] == 2 and counts["false_populations"] == 1


def test_independent_comparator_does_not_guess_ambiguous_locale():
    assert equivalent("total", "10.000", "10")
    assert not equivalent("total", "10,000", "10")
    assert not equivalent("total", "NaN", "NaN")


def test_rendering_is_byte_deterministic_for_digital_and_scan():
    cat = load(DATA / "procurement.json")
    po = cat["purchase_orders"][0]
    vendor = next(v for v in cat["vendors"] if v["id"] == po["vendor_id"])
    facts = make_invoice(po, vendor, "DETERMINISM-ONLY")
    for scan in [False, True]:
        a = draw_pdf(facts, "D0", scan, seed=7)[0]
        b = draw_pdf(facts, "D0", scan, seed=7)[0]
        assert a == b
