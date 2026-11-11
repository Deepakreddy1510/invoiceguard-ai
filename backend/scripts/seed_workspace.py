"""Add an isolated synthetic demo workspace and process real demonstration PDFs.

Never resets/upserts existing financial records. Repeatable document bytes make
re-running the sample step an exact replay rather than additional consumption.
"""

import argparse
import json
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.dialects.postgresql import insert

from app.config import DEMO_WORKSPACE_ID
from app.db import SessionLocal
from app.ingestion import ingest
from app.models import ProcessingRun, PurchaseOrder, PurchaseOrderItem, Vendor, Workspace
from app.worker.main import run_once

DEFAULT_WORKSPACE = uuid5(NAMESPACE_URL, "invoiceguard-complete-synthetic-demo")


def document(po, vendor, number, quantity, missing=False, scanned=False, copy=False):
    import pymupdf

    unit = Decimal(10) ** -(0 if po["currency"] == "JPY" else 3 if po["currency"] == "KWD" else 2)
    item = po["items"][0]
    q = Decimal(quantity)
    price = Decimal(item["unit_price"])
    rate = Decimal(item["tax_rate"])
    net = (q * price).quantize(unit, rounding=ROUND_HALF_UP)
    tax = (net * rate).quantize(unit, rounding=ROUND_HALF_UP)
    total = net + tax
    fields = [
        ("Vendor", vendor["legal_name"]),
        ("Vendor code", vendor["code"]),
        ("Tax id", vendor["tax_id"]),
        ("Invoice number", number),
        ("Invoice date", "2026-06-15"),
        ("Purchase order", po["number"]),
        ("Currency", po["currency"]),
        ("Pricing", "TAX_EXCLUSIVE"),
        ("Subtotal", str(net)),
        ("Discount", "0"),
        ("Charges", "0"),
        ("Tax", str(tax)),
        ("Grand total", str(total)),
    ]
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=720)
    page.insert_text(
        (35, 35),
        "SYNTHETIC INVOICE / DEMONSTRATION ONLY" + (" / COPY" if copy else ""),
        fontsize=14,
    )
    for i, (key, value) in enumerate(fields):
        if missing and key == "Invoice number":
            continue
        page.insert_text((35, 70 + i * 26), f"{key}: {value}", fontsize=11)
    row = f"Item: {item['sku']} | Quantity: {quantity} | Unit price: {price} | Net: {net} | Tax rate: {rate} | Tax: {tax} | Gross: {total}"
    page.insert_text(
        (35, 490), row, fontsize=min(10, 930 / max(pymupdf.get_text_length(row, fontsize=1), 1))
    )
    if scanned:
        out = pymupdf.open()
        out.new_page(width=1000, height=720).insert_image(
            pymupdf.Rect(0, 0, 1000, 720),
            stream=page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png"),
        )
        doc.close()
        doc = out
    doc.set_metadata(
        {
            "title": "Synthetic demonstration invoice",
            "creationDate": "D:20261101000000Z",
            "modDate": "D:20261101000000Z",
        }
    )
    data = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
    doc.close()
    return data


def seed(workspace_id, name):
    if workspace_id == DEMO_WORKSPACE_ID:
        raise ValueError("Refusing to mix the expanded demo with the original legacy workspace.")
    catalogue = json.loads((Path(__file__).parents[1] / "demo/procurement.json").read_text())

    def mapped(source):
        return uuid5(workspace_id, source)

    with SessionLocal.begin() as session:
        session.execute(
            insert(Workspace).values(id=workspace_id, name=name).on_conflict_do_nothing()
        )
        for v in catalogue["vendors"]:
            session.execute(
                insert(Vendor)
                .values(
                    id=mapped(v["id"]),
                    workspace_id=workspace_id,
                    code=v["code"],
                    legal_name=v["legal_name"],
                    tax_id=v["tax_id"],
                    status=v["status"],
                )
                .on_conflict_do_nothing()
            )
        for p in catalogue["purchase_orders"]:
            session.execute(
                insert(PurchaseOrder)
                .values(
                    id=mapped(p["id"]),
                    workspace_id=workspace_id,
                    vendor_id=mapped(p["vendor_id"]),
                    number=p["number"],
                    currency=p["currency"],
                    authorized_gross=Decimal(p["authorized_gross"]),
                    status=p["status"],
                    billing_mode=p["billing_mode"],
                    issued_on=date.fromisoformat(p["issued_on"]),
                    valid_until=date.fromisoformat(p["valid_until"]),
                )
                .on_conflict_do_nothing()
            )
            for i in p["items"]:
                session.execute(
                    insert(PurchaseOrderItem)
                    .values(
                        id=mapped(i["id"]),
                        po_id=mapped(p["id"]),
                        line_number=i["line_number"],
                        sku=i["sku"],
                        description=i["description"],
                        quantity=Decimal(i["quantity"]),
                        unit_price=Decimal(i["unit_price"]),
                        tax_rate=Decimal(i["tax_rate"]),
                    )
                    .on_conflict_do_nothing()
                )
    return catalogue


def process_examples(workspace_id, catalogue):
    vendors = {v["id"]: v for v in catalogue["vendors"]}
    results = []

    def submit(po, number, q, **flags):
        pdf = document(po, vendors[po["vendor_id"]], number, q, **flags)
        with SessionLocal() as session:
            receipt = ingest(
                BytesIO(pdf), number + ".pdf", None, session, workspace_id, "synthetic-demo-seeder"
            )
        for _ in range(180):
            with SessionLocal() as session:
                run = session.get(ProcessingRun, UUID(receipt["run_id"]))
                if run.status in ["SUCCEEDED", "FAILED"]:
                    break
            run_once(SessionLocal, run_id=UUID(receipt["run_id"]))
            time.sleep(0.2)
        else:
            raise RuntimeError(
                "Worker did not finish the seeded invoice; rerun safely after recovery."
            )
        results.append(receipt)

    for po in catalogue["purchase_orders"]:
        if po["status"] == "PARTIALLY_BILLED":
            submit(po, "BASELINE-" + po["number"], "2")
    paper = catalogue["purchase_orders"][0]
    services = catalogue["purchase_orders"][1]
    submit(paper, "DEMO-VALID-001", "5")
    submit(paper, "DEMO-VALID-001", "5", copy=True)
    submit(paper, "DEMO-MISSING-001", "3", missing=True)
    submit(paper, "DEMO-OVER-001", "200")
    submit(paper, "DEMO-SCAN-001", "4", scanned=True)
    for n, q in enumerate(["2", "3", "8"], 1):
        submit(services, "DEMO-PARTIAL-" + str(n), q)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=UUID, default=DEFAULT_WORKSPACE)
    parser.add_argument("--name", default="InvoiceGuard · Synthetic demonstration")
    parser.add_argument("--process-examples", action="store_true")
    args = parser.parse_args()
    catalogue = seed(args.workspace, args.name)
    results = process_examples(args.workspace, catalogue) if args.process_examples else []
    print(
        json.dumps(
            {
                "workspace_id": str(args.workspace),
                "vendors": 18,
                "purchase_orders": 36,
                "processed_example_submissions": len(results),
                "run_ids": [r["run_id"] for r in results],
            },
            indent=2,
        )
    )
