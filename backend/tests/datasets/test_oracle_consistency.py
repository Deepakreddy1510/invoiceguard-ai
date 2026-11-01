from fractions import Fraction

import pytest

from scripts.dataset_v2.common import DATA, load
from scripts.dataset_v2.integrity import validate_answers
from scripts.dataset_v2.oracle import rounded


@pytest.mark.parametrize(
    "currency,input_value,expected",
    [
        ("USD", "1.005", "1.01"),
        ("INR", "1.005", "1.01"),
        ("EUR", "1.005", "1.01"),
        ("GBP", "1.005", "1.01"),
        ("JPY", "1.5", "2"),
        ("KWD", "1.2345", "1.235"),
        ("USD", "1.0049", "1.00"),
        ("JPY", "1.49", "1"),
        ("KWD", "1.2344", "1.234"),
    ],
)
def test_independent_currency_half_up(currency, input_value, expected):
    assert rounded(input_value, currency) == Fraction(expected)


def test_development_oracles_and_source_renderings():
    # Held-out labels are deliberately not read by ordinary tests.
    assert validate_answers("development")["oracles_checked"] == 80


def test_manual_legacy_po_calculations():
    cat = load(DATA / "procurement.json")
    assert [Fraction(p["authorized_gross"]) for p in cat["purchase_orders"][:4]] == [
        2200,
        6000,
        59000,
        1000,
    ]


def test_missing_identifier_and_blocking_states_have_explicit_labels():
    cases = load(DATA / "development/answers.json")["cases"].values()
    assert all(
        a["expected_decision"] == "NEEDS_REVIEW" for a in cases if a["scenario"] == "missing_number"
    )
    assert all(
        a["expected_decision"] == "BLOCKED"
        for a in cases
        if a["scenario"]
        in ["suspended", "inactive", "closed", "cancelled", "currency_mismatch", "vendor_mismatch"]
    )


def test_partial_and_replay_oracle_sequences():
    manifest = load(DATA / "manifest.json")
    answers = load(DATA / "development/answers.json")["cases"]
    groups = {}
    for d in manifest["documents"]:
        if d["split"] == "development":
            groups.setdefault(d["group"], []).append(answers[d["id"]])
    partial = [g for g in groups.values() if g[0]["scenario"] == "partial_sequence"]
    assert len(partial) == 2
    for group in partial:
        assert [a["expected_decision"] for a in group] == [
            "VALIDATED",
            "VALIDATED",
            "VALIDATED",
            "BLOCKED",
        ]
    for group in groups.values():
        if group[0]["scenario"] == "exact_replay":
            assert group[1]["replay"] and group[1]["commitment_delta"] == "0"
