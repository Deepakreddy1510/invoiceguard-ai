"""PDF rendering consumes source facts only; no decisions or answer labels."""

import random
from io import BytesIO

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

LABELS = {
    "vendor_name": "Vendor",
    "vendor_code": "Vendor code",
    "tax_id": "Tax id",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "po_number": "Purchase order",
    "currency": "Currency",
    "pricing_mode": "Pricing",
    "subtotal": "Subtotal",
    "discount": "Discount",
    "charges": "Charges",
    "tax": "Tax",
    "total": "Grand total",
}
ITEM_LABELS = {
    "sku": "Item",
    "quantity": "Quantity",
    "unit_price": "Unit price",
    "net": "Net",
    "tax_rate": "Tax rate",
    "tax": "Tax",
    "gross": "Gross",
}


def draw_pdf(facts, layout, scan=False, seed=0, variant=0):
    rng = random.Random(seed)
    doc = pymupdf.open()
    family = int(layout[1:])
    held = layout.startswith("H")
    width, height = (1000, 720) if family % 2 == 0 else (842, 1050)
    font = ["helv", "cour", "tiro"][family % 3]
    visible = []

    def page():
        return doc.new_page(width=width, height=height)

    p = page()

    def text(p, x, y, value, size=10):
        max_width = width - x - 25
        size = min(
            size, max_width / max(pymupdf.get_text_length(value, fontname=font, fontsize=1), 1)
        )
        p.insert_text((x, y), value, fontname=font, fontsize=size, color=(0.1, 0.16, 0.2))

    text(p, 35, 35, "SYNTHETIC INVOICE - NOT PAYABLE", 16)
    text(p, 35, 52, f"Document design {layout} / revision {variant}", 8)
    field_order = list(LABELS)
    if family % 2:
        field_order = field_order[7:] + field_order[:7]
    if variant:
        field_order = list(reversed(field_order))
    y = 82
    for index, key in enumerate(field_order):
        value = facts["fields"][key]
        if value is None:
            if key == "invoice_date" and facts.get("display_ambiguous_date"):
                value = "03/04/2026"
            elif key == "po_number" and facts.get("display_ambiguous_po"):
                value = "V2-PO-UNKNOWN-A / V2-PO-UNKNOWN-B"
            else:
                continue
        shown = value
        if key == "invoice_date" and family in [3, 5] and shown == "2026-06-15":
            shown = "15 Jun 2026"
        if key in ["subtotal", "tax", "total"] and family in [4, 7] and "." in shown:
            shown = shown.replace(".", ",")
        visible.append(shown)
        label = LABELS[key]
        if family in [2, 6]:
            label = {
                "Vendor": "Supplier",
                "Invoice number": "Invoice no",
                "Purchase order": "PO",
                "Grand total": "Total due",
                "Subtotal": "Net subtotal",
            }.get(label, label)
        if family in [1, 4] or (held and family == 0):
            column = index % 2
            row = index // 2
            x = 35 + column * (width / 2)
            yy = 82 + row * 33
        else:
            x = 35
            yy = y
            y += 23
        if family in [3, 5] or (held and family == 1):
            text(p, x, yy, label.upper(), 8)
            text(p, x + 145, yy, shown, 10)
        else:
            text(p, x, yy, label + ": " + shown, 10)
    table = (held and family in [0, 1]) or (not held and family in [1, 2, 3, 4, 5, 7])
    if family in [1, 4] or (held and family == 0):
        y = 82 + 7 * 33 + 45
    elif family in [3, 5] or (held and family == 1):
        y += 25
    else:
        y += 18
    if family in [4, 7] or (held and family == 1):
        p = page()
        y = 70
        text(p, 35, 35, "SYNTHETIC INVOICE - ITEM CONTINUATION", 13)
    if table:
        headers = ["SKU", "Qty", "Unit price", "Net", "Rate", "Tax", "Gross"]
        widths = [0.04, 0.24, 0.34, 0.49, 0.63, 0.74, 0.85]
        for label, x in zip(headers, widths, strict=True):
            text(p, x * width, y, label, 9)
        y += 25
        for row in facts["items"]:
            for value, x in zip(row.values(), widths, strict=True):
                text(p, x * width, y, value, 9)
                visible.append(value)
            p.draw_line((30, y + 8), (width - 25, y + 8), color=(0.75, 0.8, 0.8))
            y += 30
    else:
        for row in facts["items"]:
            line = " | ".join(ITEM_LABELS[k] + ": " + v for k, v in row.items())
            text(p, 35, y, line, 9)
            y += 30
            visible.extend(row.values())
    text(
        p,
        35,
        height - 25,
        "Synthetic financial data. No real bank accounts or payment instructions.",
        8,
    )
    # Fixed metadata, no new trailer ID: identical inputs produce identical PDF bytes.
    doc.set_metadata(
        {
            "title": "Synthetic invoice dataset v2",
            "author": "InvoiceGuard synthetic renderer",
            "creationDate": "D:20261101000000Z",
            "modDate": "D:20261101000000Z",
        }
    )
    digital = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
    if not scan:
        doc.close()
        return digital, visible, {"dpi": None, "rotation": 0, "contrast": 1, "blur": 0}
    dpi = rng.choice([120, 150, 180])
    rotation = rng.choice([0, 0, -1, 1])
    contrast = rng.choice([0.75, 0.9, 1])
    blur = rng.choice([0, 0.3, 0.5])
    scanned = pymupdf.open()
    for source in doc:
        pix = source.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72))
        image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        image = (
            ImageEnhance.Contrast(image).enhance(contrast).filter(ImageFilter.GaussianBlur(blur))
        )
        if rotation:
            image = image.rotate(
                rotation, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white"
            )
        stream = BytesIO()
        image.save(stream, format="PNG", compress_level=6)
        scanned.new_page(width=width, height=height).insert_image(
            pymupdf.Rect(0, 0, width, height), stream=stream.getvalue()
        )
    scanned.set_metadata(doc.metadata)
    data = scanned.tobytes(garbage=4, deflate=True, no_new_id=True)
    doc.close()
    scanned.close()
    return data, visible, {"dpi": dpi, "rotation": rotation, "contrast": contrast, "blur": blur}
