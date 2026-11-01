"""Declarative synthetic procurement, independent of application seed helpers."""

from decimal import ROUND_HALF_UP, Decimal

from scripts.dataset_v2.common import UNITS, uid

HELD_VENDORS = {6, 7, 8, 9, 14, 17}


def catalogue():
    vendors = []
    names = [
        "Northstar Office Supplies",
        "Harbor IT Services",
        "Summit Logistics",
        "Cedar Lab Equipment",
        "Orchard Facilities",
        "Silverline Packaging",
        "Atlas Design Studio",
        "Juniper Electronics",
        "Meridian Calibration",
        "Seabrook Components",
        "Common Trading",
        "Common Trading",
        "Copperfield Maintenance",
        "Granite Freight",
        "Coastal Trading",
        "Cobalt Printworks",
        "Prairie Consulting",
        "Coastal Trading",
    ]
    for i, name in enumerate(names):
        status = (
            "APPROVED"
            if i in [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
            else "SUSPENDED"
            if i in [2, 13, 14, 15]
            else "INACTIVE"
        )
        vendors.append(
            {
                "id": str(__import__("uuid").UUID(int=101 + i)) if i < 3 else uid(f"vendor/{i}"),
                "code": f"SYN-{i + 1:03}" if i < 3 else f"V2-{i + 1:03}",
                "legal_name": name + " (Synthetic)",
                "tax_id": f"SYNTHETIC-TAX-{i + 1}" if i < 3 else f"SYNTHETIC-V2-TAX-{i + 1:03}",
                "status": status,
                "split": "heldout" if i in HELD_VENDORS else "development",
                "index": i,
            }
        )
    orders = []
    legacy = [
        (0, "USD", "ITEMIZED", "OPEN", "PAPER-A4", "100", "20", ".10"),
        (1, "USD", "AMOUNT_BASED", "OPEN", "IT-SUPPORT", "12", "500", "0"),
        (0, "INR", "ITEMIZED", "CLOSED", "CHAIR", "10", "5000", ".18"),
        (2, "USD", "AMOUNT_BASED", "OPEN", "FREIGHT", "1", "1000", "0"),
    ]

    def add(v, currency, mode, status, items, legacy_index=None):
        n = len(orders) + 1
        quantum = Decimal(10) ** -UNITS[currency]
        total = sum(
            (Decimal(x["quantity"]) * Decimal(x["unit_price"])).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            + (Decimal(x["quantity"]) * Decimal(x["unit_price"]) * Decimal(x["tax_rate"])).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            for x in items
        )
        po = {
            "id": str(__import__("uuid").UUID(int=201 + legacy_index))
            if legacy_index is not None
            else uid(f"po/{n}"),
            "number": f"PO-2026-{n:03}" if legacy_index is not None else f"V2-PO-{n:03}",
            "vendor_id": vendors[v]["id"],
            "vendor_index": v,
            "currency": currency,
            "billing_mode": mode,
            "status": status,
            "issued_on": "2026-01-01",
            "valid_until": "2026-12-31",
            "authorized_gross": str(total),
            "split": vendors[v]["split"],
            "items": [],
        }
        for j, item in enumerate(items, 1):
            po["items"].append(
                {
                    "id": str(__import__("uuid").UUID(int=301 + legacy_index))
                    if legacy_index is not None
                    else uid(f"item/{n}/{j}"),
                    "line_number": j,
                    **item,
                }
            )
        orders.append(po)

    for n, (v, c, m, s, sku, q, p, t) in enumerate(legacy):
        add(
            v,
            c,
            m,
            s,
            [
                {
                    "sku": sku,
                    "description": sku + " synthetic procurement",
                    "quantity": q,
                    "unit_price": p,
                    "tax_rate": t,
                }
            ],
            n,
        )
    for v in range(18):
        existing = sum(p["vendor_index"] == v for p in orders)
        for branch in range(existing, 2):
            currency = list(UNITS)[(v - 3 + branch) % 6]
            price = "20.125" if currency == "KWD" else "20" if currency == "JPY" else "20.05"
            rate = ["0", ".05", ".10", ".18", ".20", ".075"][(v + branch) % 6]
            status = (
                "PARTIALLY_BILLED"
                if v in [3, 4, 5, 6, 7, 8, 9, 12] and branch == 0
                else "CLOSED"
                if v in [9, 15, 16] and branch == 1
                else "CANCELLED"
                if v in [13, 17] and branch == 1
                else "OPEN"
            )
            items = [
                {
                    "sku": f"V2-SKU-{v + 1:02}-{j + 1}",
                    "description": ["Components", "Service periods", "Consumables"][j]
                    + " (Synthetic)",
                    "quantity": "100",
                    "unit_price": price
                    if j == 0
                    else "7.125"
                    if currency == "KWD"
                    else "7"
                    if currency == "JPY"
                    else "7.25",
                    "tax_rate": rate if j == 0 else ".05",
                }
                for j in range(3 if branch == 1 and v % 2 == 0 else 1)
            ]
            add(v, currency, "AMOUNT_BASED" if v % 4 == 0 else "ITEMIZED", status, items)
    return {
        "version": "synthetic-v2.0.0",
        "synthetic": True,
        "vendors": vendors,
        "purchase_orders": orders,
    }
