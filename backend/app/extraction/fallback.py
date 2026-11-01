"""Conservative source-backed extraction; unknown values stay null."""

import re

from app.extraction.schema import EMPTY, FIELDS, InvoiceExtraction
from app.extraction.sourcefacts import candidate, item_facts, public_fact


def candidates(pages, field, items=False):
    return [public_fact(v) for v in candidate(pages, field, items)]


def fallback(pages: list[dict]) -> InvoiceExtraction:
    data = {f: dict(EMPTY) for f in FIELDS}
    issues = []
    for field in FIELDS:
        values = candidate(pages, field)
        unique = {v["value"] for v in values}
        if len(unique) == 1:
            data[field] = public_fact(values[0])
        elif len(unique) > 1:
            issues.append(f"Ambiguous {field}: multiple source values")
    items = [{k: public_fact(v) for k, v in row.items()} for row in item_facts(pages)]
    text = "\n".join(p["text"] for p in pages)
    kind = (
        "CREDIT_NOTE"
        if re.search(r"credit\s+note", text, re.I)
        else "INVOICE"
        if re.search(r"\binvoice\b", text, re.I)
        else "UNKNOWN"
    )
    return InvoiceExtraction(document_type=kind, **data, items=items, issues=issues)
