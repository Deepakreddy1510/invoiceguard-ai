"""Independent oracle: exact rational arithmetic, no application imports."""

from fractions import Fraction

from scripts.dataset_v2.common import UNITS


def rounded(value, currency):
    """Nonnegative ROUND_HALF_UP via rational integer arithmetic."""
    x = Fraction(str(value)) * 10 ** UNITS[currency]
    return Fraction((2 * x.numerator + x.denominator) // (2 * x.denominator), 10 ** UNITS[currency])


def decimal_string(value):
    from decimal import Decimal

    return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def oracle_group(documents, cat, baseline):
    pos = {p["id"]: p for p in cat["purchase_orders"]}
    vendors = {v["id"]: v for v in cat["vendors"]}
    consumed = {key: Fraction(value) for key, value in baseline.items()}
    quantities = {}
    seen = {}
    answers = []
    for step, doc in enumerate(documents):
        facts = doc["facts"]
        f = facts["fields"]
        po = pos.get(doc["po_id"])
        vendor = vendors.get(doc["vendor_id"])
        kind = doc["scenario"]
        if kind == "exact_replay" and step == 1:
            answer = {
                **answers[0],
                "replay": True,
                "commitment_delta": "0",
                "allocations_delta": {},
                "balance_before": answers[0]["balance_after"],
                "balance_after": answers[0]["balance_after"],
            }
            answers.append(answer)
            continue
        rules = {}
        blocks = []
        reviews = []

        def rule(name, ok, severity="REVIEW", rules=rules, blocks=blocks, reviews=reviews):
            rules[name] = "PASS" if ok else severity
            if not ok:
                (blocks if severity == "BLOCK" else reviews).append(name)

        for name in [
            "invoice_number",
            "invoice_date",
            "po_number",
            "currency",
            "pricing_mode",
            "subtotal",
            "discount",
            "charges",
            "tax",
            "total",
        ]:
            rule("REQUIRED_" + name, f[name] is not None)
        rule("VENDOR_IDENTITY", vendor is not None)
        if vendor:
            rule("VENDOR_APPROVED", vendor["status"] == "APPROVED", "BLOCK")
        if po:
            rule("PO_EXISTS", True)
            rule("PO_STATUS", po["status"] in ["OPEN", "PARTIALLY_BILLED"], "BLOCK")
            rule(
                "VENDOR_PO",
                vendor is not None and vendor["id"] == po["vendor_id"],
                "BLOCK" if vendor else "REVIEW",
            )
            rule("CURRENCY", f["currency"] == po["currency"], "BLOCK")
        rule("PRICING_MODE", f["pricing_mode"] in ["TAX_EXCLUSIVE", "TAX_INCLUSIVE"])
        identity = (vendor["id"], f["invoice_number"]) if vendor and f["invoice_number"] else None
        if identity in seen:
            old = seen[identity]
            rule("BUSINESS_DUPLICATE", False, "BLOCK" if old == f["total"] else "REVIEW")
        if kind == "near_duplicate" and step == 1:
            rule("NEAR_DUPLICATE", False)
        before = (
            Fraction(po["authorized_gross"]) - consumed.get(po["id"], Fraction(0)) if po else None
        )
        total = Fraction(f["total"]) if f["total"] is not None else None
        if po and total is not None and f["currency"] == po["currency"]:
            rule("PO_BALANCE", total <= before, "BLOCK")
        allocations = {}
        if po:
            for item in facts["items"]:
                source = next((p for p in po["items"] if p["sku"] == item["sku"]), None)
                if source:
                    q = Fraction(item["quantity"])
                    allocations[source["id"]] = decimal_string(q)
                    prior = (
                        Fraction(2)
                        if po["status"] == "PARTIALLY_BILLED" and source == po["items"][0]
                        else Fraction(0)
                    )
                    used = quantities.get(source["id"], prior)
                    rule(
                        "QUANTITY_" + str(source["line_number"]),
                        used + q <= Fraction(source["quantity"]),
                        "BLOCK",
                    )
        outcome = "BLOCKED" if blocks else "NEEDS_REVIEW" if reviews else "VALIDATED"
        delta = total if outcome == "VALIDATED" else Fraction(0)
        if po and delta:
            consumed[po["id"]] = consumed.get(po["id"], Fraction(0)) + delta
            for key, q in allocations.items():
                prior = (
                    Fraction(2)
                    if po["status"] == "PARTIALLY_BILLED" and key == po["items"][0]["id"]
                    else Fraction(0)
                )
                quantities[key] = quantities.get(key, prior) + Fraction(q)
        if identity is not None and identity not in seen:
            seen[identity] = f["total"]
        answers.append(
            {
                "facts": facts,
                "scenario": kind,
                "vendor_id": doc["vendor_id"],
                "po_id": doc["po_id"],
                "expected_decision": outcome,
                "expected_rules": rules,
                "commitment_delta": decimal_string(delta or Fraction(0)),
                "allocations_delta": allocations if delta else {},
                "balance_before": decimal_string(before) if before is not None else None,
                "balance_after": decimal_string(before - delta) if before is not None else None,
                "replay": False,
            }
        )
    return answers


def validate_financial_facts(facts, currency):
    # Source changes for deliberate mismatches affect identity/currency, not invoice arithmetic.
    f = facts["fields"]
    net = tax = gross = Fraction(0)
    for item in facts["items"]:
        q = Fraction(item["quantity"])
        p = Fraction(item["unit_price"])
        r = Fraction(item["tax_rate"])
        n = (
            rounded(q * p / (1 + r) if f["pricing_mode"] == "TAX_INCLUSIVE" else q * p, currency)
            if f["pricing_mode"] in ["TAX_INCLUSIVE", "TAX_EXCLUSIVE"]
            else Fraction(item["net"])
        )
        t = (
            (
                rounded(q * p, currency) - n
                if f["pricing_mode"] == "TAX_INCLUSIVE"
                else rounded(n * r, currency)
            )
            if f["pricing_mode"] in ["TAX_INCLUSIVE", "TAX_EXCLUSIVE"]
            else Fraction(item["tax"])
        )
        assert n == Fraction(item["net"]), ("net", item)
        assert t == Fraction(item["tax"]), ("tax", item)
        assert n + t == Fraction(item["gross"])
        net += n
        tax += t
        gross += n + t
    assert net == Fraction(f["subtotal"])
    assert tax == Fraction(f["tax"])
    if f["total"] is not None:
        assert gross == Fraction(f["total"])
