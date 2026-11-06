"""Synthetic review QA workspaces. Refuse any non-disposable or hosted database."""

import json
import time
from io import BytesIO
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth import Access
from app.config import get_settings
from app.ingestion import ingest
from app.models import Decision, ProcessingRun, ReviewTask, Workspace
from app.procurement import POInput, VendorInput, create_po, create_vendor
from app.review.service import ReviewActionInput, release_held
from app.worker.main import run_once
from scripts.dataset_v2.isolation import validate_name
from scripts.generate_samples import invoice_pdf


def main():
    settings = get_settings()
    name = make_url(settings.database_url).database or ""
    if not name.endswith(("_test", "_e2e")):
        validate_name(name)
    if settings.app_environment != "local" or settings.auth_mode != "local":
        raise RuntimeError("Disposable local database required.")
    engine = create_engine(settings.database_url)
    factory = sessionmaker(engine)
    result = {}
    try:
        for label, count in [("One", 1), ("Multiple", 4), ("Empty", 0)]:
            workspace = uuid4()
            user = Access("local-demo-reviewer", workspace, "ADMIN")
            with factory.begin() as session:
                session.add(
                    Workspace(
                        id=workspace,
                        name=f"Review UX {label}",
                        kind="CUSTOM",
                        owner_subject=user.subject,
                    )
                )
                session.flush()
                vendor = create_vendor(
                    session,
                    user,
                    VendorInput(
                        legal_name="Rivermark Catering",
                        code="REVIEW-RM",
                        tax_id="SYNTHETIC-REVIEW-TAX",
                    ),
                )
                for currency in ["USD", "EUR"]:
                    create_po(
                        session,
                        user,
                        POInput(
                            number="REVIEW-PO-" + currency,
                            vendor_id=vendor.id,
                            currency=currency,
                            status="OPEN",
                            issued_on="2026-01-01",
                            valid_until="2027-12-31",
                            billing_mode="ITEMIZED",
                            authorized_gross="2200",
                            items=[
                                {
                                    "sku": "SOURCE-CHECK-REQUIRED",
                                    "description": "Synthetic catering services",
                                    "quantity": "100",
                                    "unit_price": "20",
                                    "tax_rate": "0.10",
                                }
                            ],
                        ),
                    )
            records = []
            for index in range(count):
                number = [
                    "RC-261111",
                    "INV-MAIL-EMAIL-ONLY-002",
                    "INV-UNKNOWN-SUPPLIER-003",
                    "RESOLVED-REVIEW-004",
                ][index]
                supplier = (
                    "Rivermark Catering"
                    if index != 1
                    else "Rivermark Catering and International Hospitality Procurement Services"
                )
                values = dict(
                    number=number,
                    vendor_name=supplier,
                    vendor_code="REVIEW-RM",
                    vendor_tax_id="SYNTHETIC-REVIEW-TAX",
                    po="REVIEW-PO-EUR" if index == 1 else "REVIEW-PO-USD",
                    quantity=str(index + 1),
                    subtotal=str((index + 1) * 20),
                    tax=str((index + 1) * 2),
                    total=str((index + 1) * 22),
                    currency="EUR" if index == 1 else "USD",
                )
                if index == 2:
                    values.update(
                        vendor_name="Unlisted supplier",
                        vendor_code="UNLISTED",
                        vendor_tax_id="UNLISTED-TAX",
                    )
                with factory() as session:
                    receipt = ingest(
                        BytesIO(invoice_pdf(**values)),
                        f"review-{index}.pdf",
                        None,
                        session,
                        workspace_id=workspace,
                        extraction_mode="FALLBACK",
                    )
                run_once(factory, run_id=UUID(receipt["run_id"]))
                for _ in range(100):
                    with factory() as session:
                        run = session.get(ProcessingRun, UUID(receipt["run_id"]))
                        if run.status in ["SUCCEEDED", "FAILED"]:
                            break
                    time.sleep(0.1)
                with factory.begin() as session:
                    task = session.scalar(
                        select(ReviewTask).where(
                            ReviewTask.document_id == UUID(receipt["document_id"])
                        )
                    )
                    decision = session.scalar(
                        select(Decision).where(Decision.run_id == UUID(receipt["run_id"]))
                    )
                    assert task is not None and decision.outcome == "NEEDS_REVIEW", (
                        f"Fixture {number}: {decision.outcome if decision else None}, task={task}, rules={decision.rules if decision else None}"
                    )
                    if index == 3:
                        release_held(
                            session,
                            task.id,
                            user,
                            ReviewActionInput(
                                version=task.version,
                                comment="Synthetic review resolved through the existing rejection workflow.",
                            ),
                        )
                    records.append(
                        {
                            "task_id": str(task.id),
                            "run_id": str(task.latest_run_id),
                            "number": number,
                        }
                    )
            result[label.lower()] = {"workspace_id": str(workspace), "records": records}
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
