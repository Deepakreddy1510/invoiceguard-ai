"""Independent source-identifier and business-view regressions."""

from types import SimpleNamespace

import pytest

from app.email_intake.policy import assess
from app.email_intake.screening import classify, references


@pytest.mark.parametrize(
    "text,values",
    [
        ("Invoice MAIL-PO-001", ["MAIL-PO-001"]),
        ("MAIL-PO-999", ["MAIL-PO-999"]),
        ("PO: MAIL-PO-001", ["MAIL-PO-001"]),
        ("Purchase order: AST/PO/2026/001", ["AST/PO/2026/001"]),
        ("EU_PO_2026.A2 and PO-2026-1010", ["EU_PO_2026.A2", "PO-2026-1010"]),
        ("MAIL-PO-001 MAIL-PO-001", ["MAIL-PO-001"]),
        ("MAIL-PO-001 and MAIL-PO-002", ["MAIL-PO-001", "MAIL-PO-002"]),
        ("MAIL-PO-001 is distinct from PO-001", ["MAIL-PO-001", "PO-001"]),
        ("PO--001 PO- report https://host/PO-001 person@MAIL-PO-001", []),
        ("X" * 61 + "-PO-001", []),
        ("PO: ABC-123", ["ABC-123"]),
    ],
)
def test_complete_po_identifiers_and_boundaries(text, values):
    result = references(text, "SUBJECT")
    assert [item["value"] for item in result] == values
    assert all(item["quote"] in text and item["value"] in item["quote"] for item in result)


@pytest.mark.parametrize(
    "email,pdf,review",
    [
        ("MAIL-PO-001", "MAIL-PO-001", False),
        ("MAIL-PO-999", "MAIL-PO-001", True),
        ("MAIL-PO-001", None, True),
        ("MAIL-PO-001 MAIL-PO-001", "MAIL-PO-001", False),
        ("MAIL-PO-001 MAIL-PO-999", "MAIL-PO-001", True),
        ("mail-po-001", "MAIL-PO-001", True),
        ("MAIL/PO/001", "MAIL-PO-001", True),
    ],
)
def test_exact_matching_preserves_email_review_policy(email, pdf, review):
    rules = assess(
        {"policy_version": "email-po-review-v1", "po_evidence": references(email, "BODY")},
        {"fields": {"po_number": {"value": pdf, "verified": bool(pdf)}}},
    )
    assert any(rule["outcome"] == "REVIEW" for rule in rules) == review


def test_matching_prefixed_email_does_not_raise_false_intake_conflict():
    result = classify(
        SimpleNamespace(
            subject="Invoice for MAIL-PO-001", body="MAIL-PO-001", sender="sender@example.invalid"
        ),
        SimpleNamespace(filename="invoice.pdf"),
        [{"page": 1, "method": "PDF_TEXT", "text": "INVOICE\nPurchase order: MAIL-PO-001"}],
    )
    assert result["matching_review_required"] is False
    assert {item["value"] for item in result["evidence"] if item["kind"] == "po_number"} == {
        "MAIL-PO-001"
    }


def test_business_history_filters_before_pagination_and_retains_originals(session, client):
    from app.audit import audit
    from app.config import DEMO_WORKSPACE_ID
    from app.seed import seed

    seed(session)
    for _index in range(8):
        audit(
            session,
            DEMO_WORKSPACE_ID,
            "worker",
            "WORKER_HEARTBEAT",
            {"message": "Background health probe"},
        )
    audit(
        session,
        DEMO_WORKSPACE_ID,
        "local-demo-reviewer",
        "SUPPLIER_UPDATED",
        {"message": "Supplier contact corrected"},
    )
    session.flush()
    raw = client.get("/api/v1/audit-events?limit=50").json()["events"]
    business = client.get("/api/v1/audit-events?view=business&limit=1&search=Supplier").json()[
        "events"
    ]
    assert len(business) == 1 and business[0]["action"] == "SUPPLIER_UPDATED"
    assert any(e["action"] == "WORKER_HEARTBEAT" for e in raw)
    assert not client.get("/api/v1/audit-events?view=business&actor=nobody").json()["events"]
