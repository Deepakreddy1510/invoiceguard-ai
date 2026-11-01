"""Financial construction uses Decimal; the independent validator uses Fraction."""

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal

from scripts.dataset_v2.common import UNITS


def make_invoice(po, vendor, number, quantity="3", inclusive=False, multiline=False):
    q = Decimal(quantity)
    unit = Decimal(10) ** -UNITS[po["currency"]]
    items = []
    for source in po["items"] if multiline else po["items"][:1]:
        price = Decimal(source["unit_price"])
        rate = Decimal(source["tax_rate"])
        displayed_price = price * (1 + rate) if inclusive else price
        net = (q * price).quantize(unit, rounding=ROUND_HALF_UP)
        gross = (
            (q * displayed_price).quantize(unit, rounding=ROUND_HALF_UP)
            if inclusive
            else net + (net * rate).quantize(unit, rounding=ROUND_HALF_UP)
        )
        items.append(
            {
                "sku": source["sku"],
                "quantity": str(q),
                "unit_price": str(displayed_price),
                "net": str(net),
                "tax_rate": str(rate),
                "tax": str(gross - net),
                "gross": str(gross),
            }
        )
    fields = {
        "vendor_name": vendor["legal_name"],
        "vendor_code": vendor["code"],
        "tax_id": vendor["tax_id"],
        "invoice_number": number,
        "invoice_date": "2026-06-15",
        "po_number": po["number"],
        "currency": po["currency"],
        "pricing_mode": "TAX_INCLUSIVE" if inclusive else "TAX_EXCLUSIVE",
        "subtotal": str(sum(Decimal(i["net"]) for i in items)),
        "discount": "0",
        "charges": "0",
        "tax": str(sum(Decimal(i["tax"]) for i in items)),
        "total": str(sum(Decimal(i["gross"]) for i in items)),
    }
    return {"document_type": "INVOICE", "fields": fields, "items": items, "issues": []}


def scenario_groups(cat, split):
    vendors = {v["id"]: v for v in cat["vendors"]}
    pos = [p for p in cat["purchase_orders"] if p["split"] == split]
    eligible = [
        p
        for p in pos
        if vendors[p["vendor_id"]]["status"] == "APPROVED"
        and p["status"] in ["OPEN", "PARTIALLY_BILLED"]
        and p["vendor_index"] not in [10, 11]
        and p["number"].startswith("V2-")
    ]
    single = [p for p in eligible if len(p["items"]) == 1]
    groups = []
    serial = 0

    def add(category, po=None, facts=None, count=1):
        nonlocal serial
        serial += 1
        po = po or eligible[(serial - 1) % len(eligible)]
        v = vendors[po["vendor_id"]]
        docs = []
        for step in range(count):
            data = make_invoice(
                po,
                v,
                f"V2-{split[:1].upper()}-{serial:03}-{step + 1}",
                str(3 + serial % 5),
                inclusive=serial % 4 == 0,
                multiline=serial % 3 == 0,
            )
            docs.append(
                {"facts": data, "scenario": category, "po_id": po["id"], "vendor_id": v["id"]}
            )
        groups.append(docs)
        return docs

    for n in range(32 if split == "development" else 12):
        # Includes a policy probe: unique tax/code despite an ambiguous legal name.
        probe = (
            next(p for p in pos if p["vendor_index"] == 10 and p["status"] == "OPEN")
            if split == "development" and n == 0
            else None
        )
        add("valid", probe)
    for i in range(12 if split == "development" else 6):
        kind = [
            "suspended",
            "inactive",
            "closed",
            "cancelled",
            "currency_mismatch",
            "vendor_mismatch",
        ][i % 6]
        if kind in ["suspended", "inactive"]:
            po = next(
                p
                for p in pos
                if vendors[p["vendor_id"]]["status"] == kind.upper() and p["status"] == "OPEN"
            )
        elif kind in ["closed", "cancelled"]:
            candidates = [p for p in pos if p["status"] == kind.upper()]
            # A split may have no closed PO; use any same-split ineligible PO for this violation.
            po = candidates[0] if candidates else next(p for p in pos if p["status"] == "CANCELLED")
        else:
            po = eligible[i % len(eligible)]
        doc = add(kind, po)[0]
        if kind == "currency_mismatch":
            doc["facts"]["fields"]["currency"] = "EUR" if po["currency"] != "EUR" else "USD"
        if kind == "vendor_mismatch":
            other = next(
                v
                for v in vendors.values()
                if v["split"] == split
                and v["status"] == "APPROVED"
                and v["id"] != po["vendor_id"]
                and v["index"] not in [10, 11]
            )
            doc["facts"]["fields"].update(
                vendor_name=other["legal_name"], vendor_code=other["code"], tax_id=other["tax_id"]
            )
            doc["vendor_id"] = other["id"]
    for i in range(12 if split == "development" else 6):
        kind = [
            "missing_number",
            "ambiguous_date",
            "missing_total",
            "missing_po",
            "ambiguous_vendor",
            "ambiguous_po",
        ][i % 6]
        doc = add(kind)[0]
        fields = doc["facts"]["fields"]
        field = {
            "missing_number": "invoice_number",
            "ambiguous_date": "invoice_date",
            "missing_total": "total",
            "missing_po": "po_number",
            "ambiguous_vendor": "vendor_code",
            "ambiguous_po": "po_number",
        }[kind]
        fields[field] = None
        if kind == "ambiguous_vendor":
            fields.update(
                vendor_name=("Common Trading" if split == "development" else "Coastal Trading")
                + " (Synthetic)",
                vendor_code=None,
                tax_id=None,
            )
            doc["vendor_id"] = None
        if kind in ["missing_po", "ambiguous_po"]:
            doc["po_id"] = None
    for i in range(6 if split == "development" else 4):
        kind = ["exact_replay", "business_duplicate", "near_duplicate", "conflicting_duplicate"][
            i % 4
        ]
        docs = add(kind, eligible[i % len(eligible)], count=2)
        docs[1]["facts"] = deepcopy(docs[0]["facts"])
        if kind == "near_duplicate":
            docs[1]["facts"]["fields"]["invoice_number"] += "-ALT"
        if kind == "conflicting_duplicate":
            # Different amount, same identity: preserve internal arithmetic using another quantity.
            po = next(p for p in pos if p["id"] == docs[0]["po_id"])
            docs[1]["facts"] = make_invoice(
                po, vendors[po["vendor_id"]], docs[0]["facts"]["fields"]["invoice_number"], "9"
            )
    for i in range(2):
        po = single[i % len(single)]
        docs = add("partial_sequence", po, count=4 if split == "development" else 3)
        for doc, q in zip(
            docs,
            ["10", "20", "30", "60"] if split == "development" else ["40", "35", "30"],
            strict=True,
        ):
            doc["facts"] = make_invoice(
                po, vendors[po["vendor_id"]], doc["facts"]["fields"]["invoice_number"], q
            )
    for _ in range(4 if split == "development" else 2):
        doc = add("unsupported_tax")[0]
        doc["facts"]["fields"]["pricing_mode"] = "MIXED"
    return groups
