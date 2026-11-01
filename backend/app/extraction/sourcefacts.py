"""Conservative labeled/geometry-based facts; no dataset or vendor templates."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

LABELS = {
    "vendor_name": ["vendor", "supplier", "supplier name", "vendor name"],
    "vendor_code": ["vendor code", "supplier code", "vendor id", "supplier id"],
    "tax_id": ["tax id", "tax identifier", "vat number", "gstin"],
    "invoice_number": ["invoice number", "invoice no", "invoice #", "invoice id"],
    "invoice_date": ["invoice date", "date of issue", "issue date", "date"],
    "po_number": ["purchase order", "po number", "po reference", "po", "p.o."],
    "currency": ["currency", "invoice currency"],
    "pricing_mode": ["pricing", "pricing mode", "tax mode"],
    "subtotal": ["subtotal", "net subtotal", "net amount"],
    "discount": ["discount", "discount total"],
    "charges": ["charges", "additional charges"],
    "tax": ["tax", "tax total", "vat total"],
    "total": ["grand total", "total due", "amount due", "total"],
    "sku": ["item", "sku", "item code"],
    "quantity": ["quantity", "qty"],
    "unit_price": ["unit price", "unit cost"],
    "net": ["net"],
    "tax_rate": ["tax rate", "vat rate", "rate"],
    "gross": ["gross"],
}
NUMERIC = {
    "quantity",
    "unit_price",
    "net",
    "tax_rate",
    "gross",
    "subtotal",
    "discount",
    "charges",
    "tax",
    "total",
}
ITEM_FIELDS = ["sku", "quantity", "unit_price", "net", "tax_rate", "tax", "gross"]


def normalize(field, raw):
    raw = raw.strip()
    if field in NUMERIC:
        value = raw.replace("\u00a0", "").replace(" ", "")
        percent = value.endswith("%")
        value = value.removesuffix("%")
        if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+\.\d+", value):
            value = value.replace(",", "")
        elif re.fullmatch(r"-?\d+,\d{1,2}", value):
            value = value.replace(",", ".")
        if not re.fullmatch(r"-?\d{1,14}(?:\.\d{1,6})?", value):
            return None
        try:
            number = Decimal(value)
            if not number.is_finite():
                return None
            if percent:
                if field != "tax_rate":
                    return None
                number /= 100
            return format(number, "f")
        except InvalidOperation:
            return None
    if field == "invoice_date":
        for pattern in ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]:
            try:
                return datetime.strptime(raw, pattern).date().isoformat()
            except ValueError:
                continue
        return None
    if field == "currency":
        return raw.upper() if re.fullmatch("[A-Za-z]{3}", raw) else None
    if field == "pricing_mode":
        normalized = raw.upper().replace("-", "_").replace(" ", "_")
        return (
            normalized
            if normalized in ["TAX_EXCLUSIVE", "TAX_INCLUSIVE", "MIXED", "UNKNOWN"]
            else None
        )
    if field == "po_number" and (
        re.search(r"\s(?:/|or|and)\s", raw, re.I) or not re.fullmatch(r"[\w][\w.\-/]{0,100}", raw)
    ):
        return None
    return " ".join(raw.split())


def fact(field, raw, page, quote, bbox=None):
    return {"value": normalize(field, raw), "page": page, "quote": quote, "bbox": bbox, "raw": raw}


def candidate(pages, field, item=False):
    aliases = sorted(LABELS[field], key=len, reverse=True)
    pattern = re.compile(
        r"^(?:" + "|".join(re.escape(a) for a in aliases) + r")(?:\s*[:#]\s*|\s+)(.+?)\s*$", re.I
    )
    all_labels = "|".join(re.escape(a) for names in LABELS.values() for a in names)
    found = []
    for page in pages:
        lines = page["text"].splitlines()
        lines += [
            " ".join(w["text"] for w in row["words"])
            for row in word_lines(page)
            if len(row["words"]) > 1
        ]
        for line in dict.fromkeys(lines):
            is_item = bool(re.match(r"\s*(?:Item|SKU|Item code)\s*:", line, re.I))
            if is_item != item:
                continue
            for segment in line.split("|"):
                # Prefer the longest recognized label across all fields. A
                # whitespace-delimited 'Vendor code' is not a Vendor name.
                recognized = None
                for known_field, alias in sorted(
                    ((k, a) for k, names in LABELS.items() for a in names),
                    key=lambda pair: len(pair[1]),
                    reverse=True,
                ):
                    if re.match(
                        r"^" + re.escape(alias) + r"(?:\s*[:#]\s*|\s+)(.+)$", segment.strip(), re.I
                    ):
                        recognized = known_field
                        break
                if recognized != field:
                    continue
                match = pattern.match(segment.strip())
                if match and not re.search(r"\b(?:" + all_labels + r")\s*:", match[1], re.I):
                    value = fact(field, match[1], page["page"], segment.strip())
                    if value["value"] is not None:
                        found.append(value)
    return found


def word_lines(page):
    lines = []
    for word in sorted(page.get("words", []), key=lambda w: ((w["y0"] + w["y1"]) / 2, w["x0"])):
        center = (word["y0"] + word["y1"]) / 2
        line = next((line for line in reversed(lines[-3:]) if abs(line["y"] - center) < 4), None)
        if line is None:
            line = {"y": center, "words": []}
            lines.append(line)
        line["words"].append(word)
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    return lines


def table_items(page):
    rows = []
    columns = None
    for line in word_lines(page):
        words = line["words"]
        tokens = [w["text"].casefold().strip(":") for w in words]
        labels = {}
        index = 0
        while index < len(tokens):
            token = tokens[index]
            field = None
            if (
                token == "unit"
                and index + 1 < len(tokens)
                and tokens[index + 1] in ["price", "cost"]
            ):
                field = "unit_price"
            elif token in ["sku", "item"]:
                field = "sku"
            elif token in ["qty", "quantity"]:
                field = "quantity"
            elif token in ["net", "gross", "tax"]:
                field = token
            elif token in ["rate", "vat%", "tax%"]:
                field = "tax_rate"
            if field and field not in labels:
                labels[field] = words[index]["x0"]
            index += 1
        if {"sku", "quantity", "unit_price", "net", "tax", "gross"}.issubset(labels):
            columns = sorted(labels.items(), key=lambda v: v[1])
            continue
        if not columns:
            continue
        cells = {k: [] for k, _ in columns}
        for word in words:
            center = (word["x0"] + word["x1"]) / 2
            nearest = min(columns, key=lambda col: abs(center - col[1]))[0]
            cells[nearest].append(word["text"])
        if not cells.get("sku") or not cells.get("quantity"):
            continue
        quote = " ".join(w["text"] for w in words)
        row = {
            field: fact(
                field,
                " ".join(cells.get(field, [])),
                page["page"],
                quote,
                [
                    words[0]["x0"],
                    min(w["y0"] for w in words),
                    max(w["x1"] for w in words),
                    max(w["y1"] for w in words),
                ],
            )
            for field in ITEM_FIELDS
        }
        if (
            row["quantity"]["value"] is not None
            and row["sku"]["value"]
            and any(row[f]["value"] is not None for f in ["net", "gross"])
        ):
            rows.append(row)
    return rows


def item_facts(pages):
    items = []
    for page in pages:
        for line in page["text"].splitlines():
            if re.match(r"\s*(?:Item|SKU|Item code)\s*:", line, re.I):
                source = {"page": page["page"], "text": line}
                row = {}
                for field in ITEM_FIELDS:
                    values = candidate([source], field, True)
                    row[field] = (
                        values[0]
                        if len(values) == 1
                        else {"value": None, "page": None, "quote": None}
                    )
                items.append(row)
        items.extend(table_items(page))
    return items


def public_fact(value):
    return {k: value.get(k) for k in ["value", "page", "quote"]}
