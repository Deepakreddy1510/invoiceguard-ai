from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.config import DEMO_WORKSPACE_ID
from app.extraction.pdf import read_pdf
from app.extraction.pipeline import structure
from app.models import (
    BusinessInvoice,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
)
from app.seed import seed
from app.worker.main import LostLease, finalize
from scripts.generate_samples import invoice_pdf


def prepare(session, tmp_path, **kwargs):
    data = invoice_pdf(**kwargs)
    path = tmp_path / f"{uuid4()}.pdf"
    path.write_bytes(data)
    doc = InvoiceDocument(
        workspace_id=DEMO_WORKSPACE_ID,
        sha256=str(uuid4()),
        storage_key=path.name,
        byte_size=len(data),
        page_count=1,
    )
    session.add(doc)
    session.flush()
    extraction = structure(read_pdf(str(path))["pages"], str(doc.id))
    run = ProcessingRun(
        document_id=doc.id,
        status="RUNNING",
        attempt=1,
        lease_token=uuid4(),
        lease_until=datetime.now(timezone.utc) + timedelta(seconds=180),
        extraction=extraction,
    )
    session.add(run)
    session.flush()
    return run


def test_valid_duplicate_and_idempotent_finalization(session, tmp_path):
    seed(session)
    run = prepare(session, tmp_path)
    decision = finalize(session, run.id, run.lease_token)
    assert decision.outcome == "VALIDATED", decision.rules
    assert finalize(session, run.id, run.lease_token).id == decision.id
    duplicate = prepare(session, tmp_path, alternate=True)
    blocked = finalize(session, duplicate.id, duplicate.lease_token)
    assert blocked.outcome == "BLOCKED"
    assert any(
        r["rule_id"] == "BUSINESS_DUPLICATE" and r["outcome"] == "BLOCK" for r in blocked.rules
    )
    assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 1
    assert session.scalar(select(func.count()).select_from(BusinessInvoice)) == 1


def test_partials_and_overbilling(session, tmp_path):
    seed(session)
    outcomes = []
    for n, q, net, tax, total in [
        (1, "40", "800", "80", "880"),
        (2, "35", "700", "70", "770"),
        (3, "30", "600", "60", "660"),
    ]:
        run = prepare(
            session, tmp_path, number=f"PART-{n}", quantity=q, subtotal=net, tax=tax, total=total
        )
        outcomes.append(finalize(session, run.id, run.lease_token))
    assert [d.outcome for d in outcomes] == ["VALIDATED", "VALIDATED", "BLOCKED"]
    assert outcomes[2].summary["available_before"] == "550.000000"
    rule = next(r for r in outcomes[2].rules if r["rule_id"] == "PO_BALANCE")
    assert "110.000000" in rule["explanation"]
    assert session.scalar(select(func.sum(FinancialCommitment.amount))) == Decimal("1650")


def test_missing_number_requires_review(session, tmp_path):
    seed(session)
    run = prepare(session, tmp_path, missing=True)
    assert finalize(session, run.id, run.lease_token).outcome == "NEEDS_REVIEW"
    assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 0


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("currency", "EUR", "BLOCKED"),
        ("total", "551.00", "NEEDS_REVIEW"),
        ("invoice_date", "2026-02-31", "NEEDS_REVIEW"),
        ("pricing_mode", "UNKNOWN", "NEEDS_REVIEW"),
        ("discount", "NaN", "NEEDS_REVIEW"),
    ],
)
def test_rule_failures(session, tmp_path, field, value, expected):
    seed(session)
    run = prepare(session, tmp_path)
    # Simulates an already evidence-checked source fact; rule evaluation remains deterministic.
    extraction = deepcopy(run.extraction)
    extraction["fields"][field]["value"] = value
    run.extraction = extraction
    session.flush()
    assert finalize(session, run.id, run.lease_token).outcome == expected
    assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 0


def test_unverified_value_never_validates(session, tmp_path):
    seed(session)
    run = prepare(session, tmp_path)
    extraction = deepcopy(run.extraction)
    extraction["fields"]["total"]["verified"] = False
    run.extraction = extraction
    session.flush()
    assert finalize(session, run.id, run.lease_token).outcome == "NEEDS_REVIEW"


def test_stale_worker_cannot_finalize(session, tmp_path):
    seed(session)
    run = prepare(session, tmp_path)
    with pytest.raises(LostLease):
        finalize(session, run.id, uuid4())
    assert session.scalar(select(func.count()).select_from(Decision)) == 0


@pytest.mark.parametrize(
    "settings,rule_id",
    [
        ({"po": "PO-2026-003"}, "PO_STATUS"),
        ({"po": "PO-2026-004"}, "VENDOR_PO"),
        ({"po": "NOT-AN-AUTHORIZED-PO"}, "PO_EXISTS"),
        (
            {
                "po": "PO-2026-004",
                "vendor_name": "Summit Logistics (Synthetic)",
                "vendor_code": "SYN-003",
                "vendor_tax_id": "SYNTHETIC-TAX-3",
            },
            "VENDOR_APPROVED",
        ),
        (
            {
                "unit_price": "21.00",
                "quantity": "25",
                "subtotal": "525",
                "tax": "52.50",
                "total": "577.50",
            },
            "LINE_1_PRICE",
        ),
    ],
)
def test_source_backed_procurement_violations(session, tmp_path, settings, rule_id):
    seed(session)
    run = prepare(session, tmp_path, **settings)
    decision = finalize(session, run.id, run.lease_token)
    assert decision.outcome == "BLOCKED"
    assert any(r["rule_id"] == rule_id and r["outcome"] == "BLOCK" for r in decision.rules)
    assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 0


def test_suspicious_near_duplicate_review(session, tmp_path):
    seed(session)
    a = prepare(session, tmp_path, number="NORMAL-01")
    finalize(session, a.id, a.lease_token)
    b = prepare(session, tmp_path, number="NORMAL-02")
    decision = finalize(session, b.id, b.lease_token)
    assert decision.outcome == "NEEDS_REVIEW"
    assert any(r["rule_id"] == "NEAR_DUPLICATE" for r in decision.rules)
    assert session.scalar(select(func.count()).select_from(FinancialCommitment)) == 1
