from app.extraction.fallback import fallback
from app.extraction.schema import InvoiceExtraction
from app.extraction.sourcefacts import candidate, item_facts, normalize


def compact(text):
    return " ".join(text.split()).casefold()


def equivalent(field, left, right):
    if left is None or right is None:
        return left is right
    a = normalize(field, str(left))
    b = normalize(field, str(right))
    return (
        a is not None and b is not None and compact(a) == compact(b)
        if field
        not in [
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
        ]
        else _decimal_equal(a, b)
    )


def _decimal_equal(a, b):
    from decimal import Decimal

    return a is not None and b is not None and Decimal(a) == Decimal(b)


def verify(extraction: InvoiceExtraction, pages: list[dict], document_id: str) -> dict:
    result = extraction.model_dump()
    by_page = {p["page"]: p for p in pages}
    rows = item_facts(pages)

    def supported(field, value, source):
        page = by_page.get(value["page"])
        quote = value["quote"]
        raw = value["value"]
        if raw is None or not quote or not page or compact(quote) not in compact(page["text"]):
            return None
        matches = [
            v for v in source if v["page"] == value["page"] and equivalent(field, raw, v["value"])
        ]
        return matches[0] if matches else None

    for field, value in result.items():
        if not isinstance(value, dict):
            continue
        sources = candidate(pages, field)
        selected = supported(field, value, sources)
        if selected and not all(equivalent(field, value["value"], s["value"]) for s in sources):
            selected = None
        value.update(
            verified=bool(selected),
            document_id=document_id,
            method=by_page[value["page"]]["method"] if value["page"] in by_page else None,
        )
        if selected:
            value.update(
                value=selected["value"], quote=selected["quote"], bbox=selected.get("bbox")
            )
    for item in result["items"]:
        matching = [
            row
            for row in rows
            if all(supported(field, value, [row[field]]) for field, value in item.items())
        ]
        row = matching[0] if len(matching) == 1 else None
        for field, value in item.items():
            value.update(
                verified=bool(row),
                document_id=document_id,
                method=by_page[value["page"]]["method"] if value["page"] in by_page else None,
            )
            if row:
                value.update(
                    value=row[field]["value"],
                    quote=row[field]["quote"],
                    bbox=row[field].get("bbox"),
                )
        if not row:
            result["issues"].append(
                "Line-item evidence does not identify one complete unambiguous source row."
            )
    source = fallback(pages)
    if source.document_type != extraction.document_type:
        result["issues"].append("Document type conflicts with source text.")
    if len(rows) != len(extraction.items):
        result["issues"].append("Source item count is not fully accounted for.")
    return result
