"""Synthetic renderer only; fixture expectations never enter processing logic."""

from pathlib import Path

import pymupdf


def invoice_pdf(
    number="SYN-INV-001",
    total="550.00",
    subtotal="500.00",
    tax="50.00",
    quantity="25",
    po="PO-2026-001",
    missing=False,
    alternate=False,
    scanned=False,
    vendor_name="Northstar Office Supplies (Synthetic)",
    vendor_code="SYN-001",
    vendor_tax_id="SYNTHETIC-TAX-1",
    currency="USD",
    sku="PAPER-A4",
    unit_price="20.00",
    tax_rate="0.10",
    invoice_date="2026-06-15",
    pricing_mode="TAX_EXCLUSIVE",
):
    lines = [
        "SYNTHETIC INVOICE",
        f"Vendor: {vendor_name}",
        f"Vendor code: {vendor_code}",
        f"Tax id: {vendor_tax_id}",
        f"Invoice number: {number}",
        f"Invoice date: {invoice_date}",
        f"Purchase order: {po}",
        f"Currency: {currency}",
        f"Pricing: {pricing_mode}",
        f"Subtotal: {subtotal}",
        "Discount: 0.00",
        "Charges: 0.00",
        f"Tax: {tax}",
        f"Grand total: {total}",
        f"Item: {sku} | Quantity: {quantity} | Unit price: {unit_price} | Net: {subtotal} | Tax rate: {tax_rate} | Tax: {tax} | Gross: {total}",
    ]
    if missing:
        lines = [line for line in lines if not line.startswith("Invoice number:")]
    if alternate:
        lines = [lines[0], *reversed(lines[1:])]
    doc = pymupdf.open()
    page = doc.new_page(width=1000, height=700)
    y = 50
    for line in lines:
        page.insert_text((35, y), line, fontsize=11 if scanned else 10)
        y += 30
    if scanned:
        png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
        scan = pymupdf.open()
        scan.new_page(width=1000, height=700).insert_image(
            pymupdf.Rect(0, 0, 1000, 700), stream=png
        )
        data = scan.tobytes()
        scan.close()
    else:
        data = doc.tobytes()
    doc.close()
    return data


if __name__ == "__main__":
    target = Path("../samples/invoices")
    target.mkdir(parents=True, exist_ok=True)
    cases = {
        "valid.pdf": {},
        "valid-alternate.pdf": {"alternate": True},
        "valid-scanned.pdf": {
            "scanned": True,
            "number": "SCAN-2026-01",
            "quantity": "5",
            "subtotal": "100.00",
            "tax": "10.00",
            "total": "110.00",
        },
        "duplicate-reexported.pdf": {"alternate": True},
        "missing.pdf": {"missing": True},
        "partial-1.pdf": {
            "number": "PART-1",
            "quantity": "40",
            "subtotal": "800.00",
            "tax": "80.00",
            "total": "880.00",
        },
        "partial-2.pdf": {
            "number": "PART-2",
            "quantity": "35",
            "subtotal": "700.00",
            "tax": "70.00",
            "total": "770.00",
        },
        "overbilling.pdf": {
            "number": "PART-3",
            "quantity": "30",
            "subtotal": "600.00",
            "tax": "60.00",
            "total": "660.00",
        },
    }
    for name, settings in cases.items():
        (target / name).write_bytes(invoice_pdf(**settings))
    print(f"Generated {len(cases)} synthetic PDFs.")
