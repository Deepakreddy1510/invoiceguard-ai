"""Real paginated workbench records, restricted to disposable browser databases.

No production imports this module. No live provider calls or existing workspace writes.
"""

import json
from io import BytesIO
from uuid import UUID, uuid4

import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth import Access
from app.config import get_settings
from app.ingestion import ingest
from app.models import ProcessingRun, Workspace
from app.procurement import POInput, VendorInput, create_po, create_vendor
from app.worker.main import run_once
from scripts.dataset_v2.isolation import validate_name
from scripts.generate_samples import invoice_pdf


def main():
    settings = get_settings()
    name = make_url(settings.database_url).database or ""
    if not name.endswith(("_test", "_e2e")):
        validate_name(name)
    if settings.app_environment != "local" or settings.auth_mode != "local":
        raise RuntimeError("Disposable local browser test only.")
    engine = create_engine(settings.database_url)
    factory = sessionmaker(engine)
    workspace = uuid4()
    user = Access("local-demo-reviewer", workspace, "ADMIN")
    vendor_name = "Workbench Paper and Packaging Services International"
    with factory.begin() as session:
        session.add(
            Workspace(
                id=workspace,
                name="Workbench QA workspace",
                kind="CUSTOM",
                owner_subject=user.subject,
            )
        )
        session.flush()
        for index in range(25):
            vendor = create_vendor(
                session,
                user,
                VendorInput(
                    legal_name=vendor_name if index == 0 else f"Workbench Supplier {index:02}",
                    code=f"WB-{index:02}",
                    tax_id=f"WORKBENCH-TAX-{index:02}",
                ),
            )
            create_po(
                session,
                user,
                POInput(
                    number=f"WB-PO-{index:02}",
                    vendor_id=vendor.id,
                    currency="USD",
                    status="OPEN",
                    issued_on="2026-01-01",
                    valid_until="2027-12-31",
                    billing_mode="ITEMIZED",
                    authorized_gross="22000",
                    items=[
                        {
                            "sku": "PAPER-A4",
                            "description": "Synthetic packaging supplies",
                            "quantity": "1000",
                            "unit_price": "20",
                            "tax_rate": "0.10",
                        }
                    ],
                ),
            )
    records = []
    try:
        for index in range(27):
            values = dict(
                number=f"WB-INVOICE-2026-{index:04}-SUPPLIER-REFERENCE",
                vendor_name=vendor_name,
                vendor_code="WB-00",
                vendor_tax_id="WORKBENCH-TAX-00",
                po="WB-PO-00",
                quantity=str(index + 1),
                subtotal=str((index + 1) * 20),
                tax=str((index + 1) * 2),
                total=str((index + 1) * 22),
            )
            if index == 25:
                values.update(quantity="1001", subtotal="20020", tax="2002", total="22022")
            if index == 26:
                values["missing"] = True
            pdf = pymupdf.open(stream=invoice_pdf(**values), filetype="pdf")
            page = pdf.new_page()
            page.insert_text(
                (40, 60), "SYNTHETIC SUPPORTING DELIVERY RECORD - no additional invoice amounts"
            )
            data = pdf.tobytes(garbage=4, deflate=True)
            pdf.close()
            with factory() as session:
                receipt = ingest(
                    BytesIO(data),
                    f"workbench-{index}.pdf",
                    None,
                    session,
                    workspace_id=workspace,
                    extraction_mode="FALLBACK",
                )
            run_once(factory, run_id=UUID(receipt["run_id"]))
            with factory() as session:
                run = session.get(ProcessingRun, UUID(receipt["run_id"]))
                records.append(
                    {"id": str(run.id), "document_id": str(run.document_id), "index": index}
                )
        print(json.dumps({"workspace_id": str(workspace), "records": records}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
