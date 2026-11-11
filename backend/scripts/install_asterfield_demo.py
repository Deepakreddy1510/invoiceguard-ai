"""Add-only, versioned fictional AP demonstration. No existing workspace is updated.

Run after migrations: uv run python -m scripts.install_asterfield_demo
PDFs are synthetic presentation fixtures, not an independent extraction benchmark.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select, text

from app.audit import audit
from app.config import get_settings
from app.db import SessionLocal
from app.ingestion import ingest
from app.models import (
    AuditEvent,
    Decision,
    FinancialCommitment,
    Membership,
    ProcessingRun,
    PurchaseOrder,
    PurchaseOrderItem,
    Vendor,
    Workspace,
)
from app.worker.main import run_once

VERSION = "asterfield-v1"
SEED = 20261106
ROOT = Path(__file__).parents[1] / "demo" / VERSION
COMPANY = "Asterfield Retail & Services"
NAMES = [
    "Willowbridge Office Supplies",
    "Cedarline Technology Services",
    "Maplecrest Furniture Works",
    "Larkspur Facilities Care",
    "Brookhaven Packaging",
    "Emberlane Print Studio",
    "Harbourleaf Logistics",
    "Oakmere Safety Supplies",
    "Rivermark Catering",
    "Fernwick Electrical Services",
    "Alderpath Learning",
    "Copperbrook Equipment",
    "Meadowgate Textile Supply",
    "Birchvale Analytics",
    "Hearthstone Maintenance",
    "Silverfern Design Studio",
    "Pinehaven Stationery",
    "Pinehaven Stationery Services",
]
DESCRIPTIONS = [
    "A4 office paper cartons",
    "Monthly IT support service",
    "Ergonomic task chairs",
    "Monthly office cleaning",
    "Recycled shipping cartons",
    "Retail display printing",
    "Regional delivery service",
    "Warehouse safety kits",
    "Staff event catering",
    "Lighting maintenance",
    "Staff training sessions",
    "Handheld stock scanners",
    "Staff uniform sets",
    "Monthly reporting service",
    "Equipment maintenance",
    "Store artwork service",
    "Notebook packs",
    "Printed stationery service",
]


def catalogue():
    vendors, pos = [], []
    for n, name in enumerate(NAMES):
        vendors.append(
            dict(
                code=f"AF-SUP-{n + 1:03}",
                legal_name=name,
                tax_id=f"FICTIONAL-AF-{n + 1:03}",
                status="SUSPENDED" if n == 14 else "INACTIVE" if n == 15 else "APPROVED",
            )
        )
        for part in range(2):
            index = n * 2 + part + 1
            currency = "USD" if n == 11 else "EUR" if n == 12 else "GBP" if n == 13 else "INR"
            quantity = Decimal(12 if n in [1, 3, 6, 9, 10, 13, 14, 15, 17] else 100)
            price = Decimal(250 + n * 125 + part * 50)
            rate = Decimal("0" if n == 10 else ".18" if currency == "INR" else ".10")
            gross = (quantity * price * (1 + rate)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            pos.append(
                dict(
                    number=f"AF-PO-2026-{index:03}",
                    vendor_index=n,
                    currency=currency,
                    authorized_gross=str(gross),
                    billing_mode="AMOUNT_BASED" if quantity == 12 else "ITEMIZED",
                    status="CLOSED"
                    if index in [30, 32, 36]
                    else "CANCELLED"
                    if index == 35
                    else "OPEN",
                    issued_on="2026-01-01",
                    valid_until="2027-12-31",
                    items=[
                        dict(
                            line_number=1,
                            sku=f"AF-{n + 1:03}",
                            description=DESCRIPTIONS[n],
                            quantity=str(quantity),
                            unit_price=str(price),
                            tax_rate=str(rate),
                        )
                    ],
                )
            )
    return dict(
        version=VERSION,
        random_seed=SEED,
        synthetic=True,
        company=COMPANY,
        vendors=vendors,
        purchase_orders=pos,
    )


def cases():
    # Independent expected outcomes and arithmetic; never derived from engine output.
    return [
        dict(file="01-office-supplies.pdf", po=1, number="WB-261101", q="10", expected="VALIDATED"),
        dict(
            file="02-it-support-october.pdf", po=3, number="CL-261001", q="2", expected="VALIDATED"
        ),
        dict(
            file="03-it-support-november.pdf", po=3, number="CL-261102", q="3", expected="VALIDATED"
        ),
        dict(
            file="04-it-support-over-budget.pdf",
            po=3,
            number="CL-261103",
            q="8",
            expected="BLOCKED",
        ),
        dict(file="05-chairs-digital.pdf", po=5, number="MC-261105", q="4", expected="VALIDATED"),
        dict(
            file="06-cleaning-scan.pdf",
            po=7,
            number="LF-261106",
            q="2",
            expected="VALIDATED",
            scan=True,
        ),
        dict(
            file="07-packaging-photo.pdf",
            po=9,
            number="BP-261107",
            q="8",
            expected="VALIDATED",
            photo=True,
        ),
        dict(
            file="08-printing.pdf",
            po=11,
            number="EP-261108",
            q="5",
            expected="VALIDATED",
            inclusive=True,
        ),
        dict(
            file="09-delivery-service.pdf", po=13, number="HL-261109", q="2", expected="VALIDATED"
        ),
        dict(file="10-safety-kits.pdf", po=15, number="OS-261110", q="6", expected="VALIDATED"),
        dict(
            file="11-catering-missing-reference.pdf",
            po=17,
            number="RC-261111",
            q="3",
            expected="NEEDS_REVIEW",
            missing=True,
        ),
        dict(file="12-electrical.pdf", po=19, number="FE-261112", q="1", expected="VALIDATED"),
        dict(
            file="13-training-tax-exempt.pdf",
            po=21,
            number="AL-261113",
            q="2",
            expected="VALIDATED",
        ),
        dict(file="14-scanners-usd.pdf", po=23, number="CE-261114", q="5", expected="VALIDATED"),
        dict(file="15-uniforms-eur.pdf", po=25, number="MT-261115", q="5", expected="VALIDATED"),
        dict(file="16-analytics-gbp.pdf", po=27, number="BA-261116", q="2", expected="VALIDATED"),
        dict(
            file="17-suspended-supplier.pdf", po=29, number="HM-261117", q="1", expected="BLOCKED"
        ),
        dict(file="18-inactive-supplier.pdf", po=31, number="SD-261118", q="1", expected="BLOCKED"),
        dict(file="19-closed-order.pdf", po=36, number="PS-261119", q="1", expected="BLOCKED"),
        dict(
            file="20-office-supplies-copy.pdf",
            po=1,
            number="WB-261101",
            q="10",
            expected="BLOCKED",
            copy=True,
        ),
        dict(
            file="21-supplier-order-mismatch.pdf",
            po=2,
            number="CL-261121",
            q="1",
            expected="BLOCKED",
            vendor_index=1,
        ),
    ]


def invoice(case, catalog, layout):
    import pymupdf

    po = catalog["purchase_orders"][case["po"] - 1]
    vendor = catalog["vendors"][case.get("vendor_index", po["vendor_index"])]
    item = po["items"][0]
    net = (Decimal(case["q"]) * Decimal(item["unit_price"])).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )
    tax = (net * Decimal(item["tax_rate"])).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    displayed_price = (
        Decimal(item["unit_price"]) * (1 + Decimal(item["tax_rate"]))
        if case.get("inclusive")
        else Decimal(item["unit_price"])
    )
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=780)
    accent = [(0.65, 0.27, 0.17), (0.15, 0.30, 0.27), (0.25, 0.28, 0.40)][layout]
    page.draw_rect(pymupdf.Rect(0, 0, 1000, 85), color=None, fill=accent)
    page.insert_text((38, 36), vendor["legal_name"], fontsize=22, color=(1, 1, 1))
    page.insert_text(
        (38, 65),
        "INVOICE" + (" / DUPLICATE COPY" if case.get("copy") else ""),
        fontsize=13,
        color=(1, 1, 1),
    )
    page.insert_text((38, 112), f"Bill to: {COMPANY}", fontsize=13)
    fields = [
        ("Vendor", vendor["legal_name"]),
        ("Vendor code", vendor["code"]),
        ("Tax id", vendor["tax_id"]),
        ("Invoice number", case["number"]),
        ("Invoice date", "2026-11-01"),
        ("Purchase order", po["number"]),
        ("Currency", po["currency"]),
        ("Pricing", "TAX_INCLUSIVE" if case.get("inclusive") else "TAX_EXCLUSIVE"),
        ("Subtotal", str(net)),
        ("Discount", "0"),
        ("Charges", "0"),
        ("Tax", str(tax)),
        ("Grand total", str(net + tax)),
    ]
    # Three genuinely different panel arrangements retain ordinary, legible field labels.
    for i, (label, value) in enumerate(fields):
        if case.get("missing") and label == "Purchase order":
            continue
        per_panel = 8 if layout == 2 else 7
        col = 0 if layout == 0 else i // per_panel
        row = i if layout == 0 else i % per_panel
        x = 38 + col * (500 if layout == 2 else 470)
        y = (180 if layout == 2 and col else 155) + row * (
            25 if layout == 0 else 37 if layout == 2 else 39
        )
        page.insert_text((x, y), f"{label}: {value}", fontsize=12)
    page.draw_rect(
        pymupdf.Rect(30, 505, 970, 605), color=(0.8, 0.77, 0.72), fill=(0.97, 0.96, 0.93)
    )
    page.insert_text((40, 530), item["description"], fontsize=13)
    row = f"Item: {item['sku']} | Quantity: {case['q']} | Unit price: {displayed_price} | Net: {net} | Tax rate: {item['tax_rate']} | Tax: {tax} | Gross: {net + tax}"
    page.insert_text(
        (40, 567), row, fontsize=min(11, 910 / pymupdf.get_text_length(row, fontsize=1))
    )
    page.insert_text(
        (40, 660),
        "Payment terms: 30 days from invoice date. No bank details are provided for this sample.",
        fontsize=11,
    )
    page.insert_text(
        (40, 710),
        "Sample company data. No payments are executed. All suppliers and tax identifiers are fictional.",
        fontsize=10,
        color=(0.4, 0.4, 0.4),
    )
    if case.get("scan") or case.get("photo"):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        out = pymupdf.open()
        target = out.new_page(width=1000, height=780)
        image = pix.tobytes("png")
        if case.get("photo"):
            from PIL import Image, ImageEnhance

            im = Image.open(BytesIO(image)).convert("RGB")
            im = ImageEnhance.Contrast(im).enhance(0.86)
            im = im.rotate(0.6, resample=Image.Resampling.BICUBIC, fillcolor=(238, 235, 228))
            stream = BytesIO()
            im.save(stream, format="JPEG", quality=90)
            image = stream.getvalue()
        target.insert_image(target.rect, stream=image)
        doc.close()
        doc = out
    doc.set_metadata(
        dict(
            title="Fictional supplier invoice · " + case["number"],
            creationDate="D:20261106000000Z",
            modDate="D:20261106000000Z",
        )
    )
    result = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
    doc.close()
    return result


def generate(root=ROOT):
    root.mkdir(parents=True, exist_ok=True)
    catalog = catalogue()
    manifest = []
    for i, case in enumerate(cases()):
        data = invoice(case, catalog, i % 3)
        (root / case["file"]).write_bytes(data)
        manifest.append(
            {
                **case,
                "layout": ["letterhead", "split-panels", "statement-panels"][i % 3],
                "medium": "photographed"
                if case.get("photo")
                else "scanned"
                if case.get("scan")
                else "digital",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    (root / "procurement.json").write_text(json.dumps(catalog, indent=2) + "\n")
    (root / "manifest.json").write_text(
        json.dumps(dict(version=VERSION, seed=SEED, synthetic=True, documents=manifest), indent=2)
        + "\n"
    )
    return catalog, manifest


def install(subject="local-demo-reviewer"):
    if get_settings().auth_mode != "local":
        raise ValueError(
            "This installer is for local demonstrations. Hosted provisioning requires a separate administrator-reviewed membership setup."
        )
    if subject != "local-demo-reviewer":
        raise ValueError("Local installer only grants the configured local demonstration identity.")
    catalog, manifest = generate()
    wid = uuid5(NAMESPACE_URL, "invoiceguard:" + VERSION + ":" + subject)

    def ident(value):
        return uuid5(wid, value)

    with SessionLocal() as lock_session:
        lock_session.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key,0))"), dict(key=str(wid))
        )
        try:
            return _install(wid, subject, catalog, manifest, ident)
        finally:
            lock_session.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"), dict(key=str(wid))
            )


def _install(wid, subject, catalog, manifest, ident):
    with SessionLocal.begin() as s:
        workspace = s.get(Workspace, wid)
        if not workspace:
            s.add(
                Workspace(
                    id=wid, name=COMPANY + " · Sample company", kind="CUSTOM", owner_subject=subject
                )
            )
            s.flush()
            s.add(Membership(workspace_id=wid, subject=subject, role="ADMIN"))
            for v in catalog["vendors"]:
                s.add(Vendor(id=ident(v["code"]), workspace_id=wid, **v))
            s.flush()
            for p in catalog["purchase_orders"]:
                v = catalog["vendors"][p["vendor_index"]]
                s.add(
                    PurchaseOrder(
                        id=ident(p["number"]),
                        workspace_id=wid,
                        vendor_id=ident(v["code"]),
                        **{
                            k: p[k]
                            for k in [
                                "number",
                                "currency",
                                "authorized_gross",
                                "billing_mode",
                                "status",
                            ]
                        },
                        issued_on=date.fromisoformat(p["issued_on"]),
                        valid_until=date.fromisoformat(p["valid_until"]),
                    )
                )
                s.flush()
                for item in p["items"]:
                    s.add(
                        PurchaseOrderItem(
                            id=ident(p["number"] + item["sku"]), po_id=ident(p["number"]), **item
                        )
                    )
            audit(
                s,
                wid,
                subject,
                "SAMPLE_COMPANY_CREATED",
                dict(version=VERSION, seed=SEED, synthetic=True),
            )
        elif workspace.owner_subject != subject or workspace.name != COMPANY + " · Sample company":
            raise ValueError("Workspace identity collision; no existing data was changed.")
    results = []
    expected_reserved = {}
    for case in manifest:
        with SessionLocal() as s:
            receipt = ingest(
                BytesIO((ROOT / case["file"]).read_bytes()),
                case["file"],
                VERSION + ":" + case["file"],
                s,
                wid,
                subject,
                extraction_mode="FALLBACK",
            )
        rid = UUID(receipt["run_id"])
        for _ in range(240):
            with SessionLocal() as s:
                run = s.get(ProcessingRun, rid)
                if run.status in ["SUCCEEDED", "FAILED"]:
                    break
            run_once(SessionLocal, run_id=rid)
            time.sleep(0.25)
        with SessionLocal() as s:
            run = s.get(ProcessingRun, rid)
            decision = s.scalar(select(Decision).where(Decision.run_id == rid))
            actual = decision.outcome if decision else run.status
            if actual != case["expected"]:
                raise RuntimeError(
                    f"{case['file']}: expected {case['expected']}, observed {actual}. Workspace remains unverified; inspect persisted evidence."
                )
            if case["medium"] != "digital" and not any(p["method"] == "OCR" for p in run.pages):
                raise RuntimeError("OCR was not observed")
            if (
                case.get("inclusive")
                and run.extraction["fields"]["pricing_mode"]["value"] != "TAX_INCLUSIVE"
            ):
                raise RuntimeError("Tax-inclusive source evidence was not extracted correctly")
            results.append(
                dict(
                    file=case["file"],
                    expected=case["expected"],
                    actual=actual,
                    actual_provider=run.extraction["provider"],
                    ocr_pages=[p["page"] for p in run.pages if p["method"] == "OCR"],
                    run_id=str(rid),
                    po=catalog["purchase_orders"][case["po"] - 1]["number"],
                )
            )
            if actual == "VALIDATED":
                p = catalog["purchase_orders"][case["po"] - 1]
                item = p["items"][0]
                net = (Decimal(case["q"]) * Decimal(item["unit_price"])).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                )
                tax = (net * Decimal(item["tax_rate"])).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP
                )
                expected_reserved[p["number"]] = (
                    expected_reserved.get(p["number"], Decimal(0)) + net + tax
                )
    balances = []
    with SessionLocal.begin() as s:
        for p in catalog["purchase_orders"]:
            reserved = s.scalar(
                select(func.coalesce(func.sum(FinancialCommitment.amount), 0)).where(
                    FinancialCommitment.po_id == ident(p["number"]),
                    FinancialCommitment.status.in_(["RESERVED", "HELD", "SETTLED"]),
                )
            )
            if reserved != expected_reserved.get(p["number"], Decimal(0)):
                raise RuntimeError("Reservation mismatch: " + p["number"])
            po_record = s.get(PurchaseOrder, ident(p["number"]))
            if (
                reserved > 0
                and reserved < Decimal(p["authorized_gross"])
                and po_record.status == "OPEN"
            ):
                # Only this version's newly created sample orders, after real commitments.
                po_record.status = "PARTIALLY_BILLED"
            balances.append(
                dict(
                    po=p["number"],
                    authorised=p["authorized_gross"],
                    reserved=str(reserved),
                    remaining=str(Decimal(p["authorized_gross"]) - reserved),
                )
            )
        verified = s.scalar(
            select(AuditEvent.id).where(
                AuditEvent.workspace_id == wid, AuditEvent.action == "SAMPLE_COMPANY_VERIFIED"
            )
        )
        if not verified:
            audit(
                s,
                wid,
                subject,
                "SAMPLE_COMPANY_VERIFIED",
                dict(version=VERSION, documents=len(results), balances=balances),
            )
        s.get(
            Workspace, wid
        ).kind = "DEMO"  # Preferred only after actual decisions and balances verified.
    report = dict(
        version=VERSION,
        workspace_id=str(wid),
        vendors=18,
        purchase_orders=36,
        documents=len(results),
        outcomes=dict(Counter(r["actual"] for r in results)),
        results=results,
        balances=balances,
        live_gemini_tested=False,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = (
        dict(version=VERSION, documents=len(generate()[1])) if args.generate_only else install()
    )
    content = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(content)
    print(content)
