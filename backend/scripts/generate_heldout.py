"""Independent synthetic layouts; expected values are hand-labeled in manifest.json."""

from pathlib import Path

import pymupdf

ROOT = Path("../samples/extraction")


def generate():
    ROOT.mkdir(parents=True, exist_ok=True)
    # Unlike the development renderer, key aliases, ordering and pagination differ.
    for name, number, _missing, scan in [
        ("heldout-digital", "HO-731", False, False),
        ("heldout-scan", "HO-854", False, True),
        ("heldout-missing", None, True, False),
    ]:
        doc = pymupdf.open()
        page = doc.new_page(width=1000, height=720)
        left = [
            "INVOICE - SYNTHETIC EVALUATION",
            "Supplier: Northstar Office Supplies (Synthetic)",
            "Currency: USD",
            "PO: PO-2026-001",
            "Date: 2026-05-20",
        ]
        if number:
            left.append("Invoice no: " + number)
        right = [
            "Pricing mode: TAX_EXCLUSIVE",
            "Net subtotal: 60.00",
            "Tax total: 6.00",
            "Total due: 66.00",
            "Charges: 0.00",
            "Discount: 0.00",
        ]
        for column, x in [(left, 40), (right, 530)]:
            for n, line in enumerate(column):
                page.insert_text((x, 50 + n * 38), line, fontsize=12)
        page = doc.new_page(width=1000, height=720)
        page.insert_text(
            (35, 80),
            "Item: PAPER-A4 | Qty: 3 | Unit price: 20.00 | Net: 60.00 | Tax rate: 0.10 | Tax: 6.00 | Gross: 66.00",
            fontsize=11,
        )
        if scan:
            scanned = pymupdf.open()
            for page in doc:
                scanned.new_page(width=1000, height=720).insert_image(
                    pymupdf.Rect(0, 0, 1000, 720),
                    stream=page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png"),
                )
            scanned.save(ROOT / (name + ".pdf"))
            scanned.close()
        else:
            doc.save(ROOT / (name + ".pdf"))
        doc.close()


if __name__ == "__main__":
    generate()
