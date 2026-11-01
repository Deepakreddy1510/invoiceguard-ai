from collections import Counter

from scripts.dataset_v2.common import DATA, load
from scripts.dataset_v2.integrity import validate_catalogue, validate_public


def test_catalogue_counts_and_financial_integrity():
    assert validate_catalogue(load(DATA / "procurement.json"))


def test_public_split_and_all_document_hashes():
    result = validate_public()
    assert result["hashes_verified"] == 128
    assert result["scan_count"] == 46


def test_partial_po_baselines_are_real_inputs():
    data = load(DATA / "manifest.json")
    cat = load(DATA / "procurement.json")
    assert {b["po_id"] for b in data["baseline"]} == {
        p["id"] for p in cat["purchase_orders"] if p["status"] == "PARTIALLY_BILLED"
    }
    assert all(b["quantity"] == "2" for b in data["baseline"])


def test_all_currencies_and_split_procurement():
    cat = load(DATA / "procurement.json")
    assert {p["currency"] for p in cat["purchase_orders"]} == {
        "USD",
        "INR",
        "EUR",
        "GBP",
        "JPY",
        "KWD",
    }
    assert Counter(p["split"] for p in cat["purchase_orders"]) == {"development": 24, "heldout": 12}
