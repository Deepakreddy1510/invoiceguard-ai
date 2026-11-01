"""Deterministic supported-scope rules, called inside locked finalization."""

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models import (
    BusinessInvoice,
    CommitmentAllocation,
    FinancialCommitment,
    InvoiceDocument,
    PurchaseOrder,
    PurchaseOrderItem,
    Vendor,
)

CONSUMING = ("RESERVED", "HELD", "SETTLED")
CURRENCY_UNITS = {
    "USD": Decimal(".01"),
    "INR": Decimal(".01"),
    "EUR": Decimal(".01"),
    "GBP": Decimal(".01"),
    "JPY": Decimal("1"),
    "KWD": Decimal(".001"),
}


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def evaluate(session, run, extraction, replace_invoice_id=None):
    workspace_id = session.get(InvoiceDocument, run.document_id).workspace_id
    fields = extraction["fields"]
    rules = []
    allocations = {}
    invoice = None
    po = None
    vendor = None

    def result(code, condition, detail, actual=None, expected=None, failure="REVIEW"):
        rules.append(
            {
                "rule_id": code,
                "outcome": "PASS" if condition else failure,
                "explanation": detail,
                "actual": str(actual) if actual is not None else None,
                "expected": str(expected) if expected is not None else None,
            }
        )

    def value(name, source=fields):
        field = source.get(name, {})
        return field.get("value") if field.get("verified") else None

    def number(name, source=fields):
        raw = value(name, source)
        if raw is None or not re.fullmatch(r"-?\d{1,14}(?:\.\d{1,6})?", raw):
            return None
        try:
            n = Decimal(raw)
            return n if n.is_finite() else None
        except InvalidOperation:
            return None

    result(
        "EXTRACTION_ISSUES",
        not fields.get("issues"),
        "Extraction ambiguities require review: " + "; ".join(fields.get("issues", [])),
    )
    critical = [
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
    ]
    for field in critical:
        result("REQUIRED_" + field, bool(value(field)), f"{field}: verified source value required.")
    result(
        "DOCUMENT_TYPE",
        fields["document_type"] == "INVOICE",
        "Only supported positive invoices may validate.",
    )
    total = number("total")
    subtotal = number("subtotal")
    tax = number("tax")
    discount = number("discount")
    charges = number("charges")
    for field in ["total", "subtotal", "tax", "discount", "charges"]:
        n = number(field)
        result(
            "DECIMAL_" + field,
            n is not None and n >= 0 and (field != "total" or n > 0),
            f"{field}: finite, supported nonnegative decimal required; total must be positive.",
        )
    inv_date = None
    try:
        inv_date = date.fromisoformat(value("invoice_date") or "")
    except ValueError:
        pass
    result(
        "DATE",
        bool(inv_date and inv_date <= datetime.now(ZoneInfo("Asia/Kolkata")).date()),
        "Invoice date must be unambiguous ISO date, not in the future.",
    )
    currency = value("currency")
    unit = CURRENCY_UNITS.get(currency)
    result("SUPPORTED_CURRENCY", bool(unit), "Currency must be in the supported minor-unit policy.")
    if unit and total is not None:
        result(
            "MINOR_UNITS",
            total == total.quantize(unit),
            "Total must respect currency minor units.",
            total,
            unit,
        )
    code = value("vendor_code")
    name = value("vendor_name")
    tax_id = value("tax_id")
    vendors = session.scalars(select(Vendor).where(Vendor.workspace_id == workspace_id)).all()
    # Strong identifiers constrain identity. A shared name cannot override a
    # unique vendor code/tax ID; contradictory strong identifiers remain review.
    strong = []
    if code:
        strong.append({v.id for v in vendors if normalize(v.code) == normalize(code)})
    if tax_id:
        strong.append(
            {v.id for v in vendors if v.tax_id and normalize(v.tax_id) == normalize(tax_id)}
        )
    ids = (
        set.intersection(*strong)
        if strong
        else {v.id for v in vendors if name and normalize(v.legal_name) == normalize(name)}
    )
    matches = [v for v in vendors if v.id in ids]
    if len(matches) == 1:
        vendor = matches[0]
    result(
        "VENDOR_IDENTITY",
        vendor is not None,
        "Vendor must resolve unambiguously using supported source identifiers.",
    )
    if vendor:
        consistent = (
            (not code or normalize(code) == normalize(vendor.code))
            and (not tax_id or (vendor.tax_id and normalize(tax_id) == normalize(vendor.tax_id)))
            and (not name or normalize(name) == normalize(vendor.legal_name))
        )
        result("VENDOR_CONSISTENCY", consistent, "All supplied vendor identifiers must agree.")
        result(
            "VENDOR_APPROVED",
            vendor.status == "APPROVED",
            f"Vendor {vendor.code} is {vendor.status}.",
            failure="BLOCK",
        )
    ref = value("po_number")
    if ref:
        po = session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.workspace_id == workspace_id, PurchaseOrder.number == ref)
            .with_for_update()
        )
        result("PO_EXISTS", po is not None, f"Referenced PO {ref} must exist.", failure="BLOCK")
    if po:
        result(
            "VENDOR_PO",
            vendor is not None and vendor.id == po.vendor_id,
            "Invoice vendor must match PO vendor.",
            failure="BLOCK" if vendor else "REVIEW",
        )
        result(
            "PO_STATUS",
            po.status in ("OPEN", "PARTIALLY_BILLED"),
            f"PO {po.number} is {po.status}.",
            failure="BLOCK",
        )
        result(
            "CURRENCY",
            currency == po.currency,
            f"Invoice currency {currency}; PO currency {po.currency}.",
            failure="BLOCK" if currency else "REVIEW",
        )
        result(
            "PO_DATES",
            bool(inv_date and po.issued_on <= inv_date <= po.valid_until),
            "Invoice date must fall within PO validity.",
        )
    mode = value("pricing_mode")
    result(
        "PRICING_MODE",
        mode in ("TAX_EXCLUSIVE", "TAX_INCLUSIVE"),
        "Tax mode must be supported and explicit.",
    )
    result(
        "ADJUSTMENTS",
        discount == 0 and charges == 0,
        "Nonzero header discounts/charges require allocation review in this version.",
    )
    if all(n is not None for n in (subtotal, tax, total, discount, charges)) and unit:
        expected = (subtotal - discount + charges + tax).quantize(unit, rounding=ROUND_HALF_UP)
        result(
            "GRAND_TOTAL",
            abs(total - expected) <= unit,
            "Grand total must reconcile with subtotal, tax and adjustments.",
            total,
            expected,
        )
    line_nets = []
    line_taxes = []
    line_gross = []
    items = fields.get("items", [])
    result(
        "LINE_EVIDENCE",
        bool(items) or bool(po and po.billing_mode == "AMOUNT_BASED" and tax == 0),
        "Item evidence required; zero-tax amount-based bundled billing may use header amounts.",
    )
    po_items = (
        session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)).all()
        if po
        else []
    )
    for index, item in enumerate(items, 1):
        q = number("quantity", item)
        price = number("unit_price", item)
        net = number("net", item)
        rate = number("tax_rate", item)
        ltax = number("tax", item)
        gross = number("gross", item)
        complete = all(n is not None for n in (q, price, net, rate, ltax, gross))
        result(
            f"LINE_{index}_FIELDS",
            complete,
            f"Line {index}: all arithmetic fields need verified evidence.",
        )
        if not complete:
            continue
        result(
            f"LINE_{index}_SIGNS",
            q > 0 and price >= 0 and net >= 0 and 0 <= rate <= 1 and ltax >= 0 and gross >= 0,
            f"Line {index}: positive quantity and supported nonnegative values required.",
        )
        if not (q > 0 and price >= 0 and 0 <= rate <= 1) or not unit:
            continue
        calc_net = (q * price if mode == "TAX_EXCLUSIVE" else q * price / (1 + rate)).quantize(
            unit, rounding=ROUND_HALF_UP
        )
        calc_tax = (
            (calc_net * rate).quantize(unit, rounding=ROUND_HALF_UP)
            if mode == "TAX_EXCLUSIVE"
            else (q * price).quantize(unit, rounding=ROUND_HALF_UP) - calc_net
        )
        result(
            f"LINE_{index}_ARITHMETIC",
            abs(net - calc_net) <= unit
            and abs(ltax - calc_tax) <= unit
            and abs(gross - net - ltax) <= unit,
            f"Line {index}: quantity, price, net, tax and gross must reconcile.",
            f"{net}/{ltax}/{gross}",
            f"{calc_net}/{calc_tax}/{calc_net + calc_tax}",
        )
        line_nets.append(net)
        line_taxes.append(ltax)
        line_gross.append(gross)
        matched = [p for p in po_items if p.sku == value("sku", item)]
        if len(matched) == 1:
            p = matched[0]
            allocations[p.id] = allocations.get(p.id, Decimal(0)) + q
            net_price = price if mode == "TAX_EXCLUSIVE" else price / (1 + rate)
            result(
                f"LINE_{index}_PRICE",
                net_price <= p.unit_price,
                "Unit price cannot exceed PO authorization.",
                net_price,
                p.unit_price,
                failure="BLOCK",
            )
            result(
                f"LINE_{index}_TAX",
                rate == p.tax_rate,
                "Tax rate must match the stored PO policy.",
                rate,
                p.tax_rate,
            )
        else:
            result(
                f"LINE_{index}_MATCH",
                bool(po and po.billing_mode == "AMOUNT_BASED"),
                f"Line {index}: item-controlled POs require exact SKU matching.",
            )
    if items and len(line_nets) == len(items) and unit:
        result(
            "SUBTOTAL",
            subtotal is not None and abs(sum(line_nets) - subtotal) <= unit,
            "Subtotal must equal sum of line net amounts.",
            subtotal,
            sum(line_nets),
        )
        result(
            "TAX",
            tax is not None and abs(sum(line_taxes) - tax) <= unit,
            "Tax total must equal sum of line taxes.",
            tax,
            sum(line_taxes),
        )
        result(
            "LINE_GROSS",
            total is not None
            and discount == 0
            and charges == 0
            and abs(sum(line_gross) - total) <= unit,
            "Invoice gross must reconcile with line gross.",
            total,
            sum(line_gross),
        )
    if not items:
        result(
            "HEADER_TAX",
            tax == 0,
            "Without supported tax lines only explicit zero-tax bundled billing may validate.",
        )
    inv_number = value("invoice_number")
    if inv_number and len(inv_number) > 160:
        result("INVOICE_NUMBER_LENGTH", False, "Invoice number exceeds supported length.")
        inv_number = None
    if vendor and inv_number:
        identity = f"{vendor.id}:{normalize(inv_number)}"
        replacing = session.get(BusinessInvoice, replace_invoice_id) if replace_invoice_id else None
        other = session.scalar(
            select(BusinessInvoice).where(
                BusinessInvoice.workspace_id == workspace_id,
                BusinessInvoice.identity_key == identity,
            )
        )
        if replacing and other and other.id != replacing.id:
            result(
                "CORRECTION_IDENTITY_COLLISION",
                False,
                "Correction identifies another existing business invoice; resolve the duplicate before proceeding.",
                failure="BLOCK",
            )
            invoice = replacing
            invoice_id = replacing.id
        elif replacing:
            invoice = replacing
            invoice_id = replacing.id
            session.flush()
        else:
            invoice_id = session.scalar(
                insert(BusinessInvoice)
                .values(
                    workspace_id=workspace_id,
                    vendor_id=vendor.id,
                    identity_key=identity,
                    source_document_id=run.document_id,
                    invoice_number=inv_number,
                    invoice_date=inv_date,
                    currency=currency if unit else None,
                    total=total,
                )
                .on_conflict_do_nothing(index_elements=["workspace_id", "identity_key"])
                .returning(BusinessInvoice.id)
            )
            invoice = session.scalar(
                select(BusinessInvoice)
                .where(
                    BusinessInvoice.workspace_id == workspace_id,
                    BusinessInvoice.identity_key == identity,
                )
                .with_for_update()
            )
        if (
            not replace_invoice_id
            and invoice_id is None
            and invoice.source_document_id != run.document_id
        ):
            conflict = (
                invoice.total != total
                or invoice.currency != currency
                or invoice.invoice_date != inv_date
            )
            result(
                "BUSINESS_DUPLICATE",
                False,
                f"Existing vendor invoice {invoice.invoice_number}; original document {invoice.source_document_id}. "
                + (
                    "Conflicting facts require review."
                    if conflict
                    else "Confirmed duplicate business invoice."
                ),
                failure="REVIEW" if conflict else "BLOCK",
            )
        near = (
            session.scalar(
                select(BusinessInvoice)
                .where(
                    BusinessInvoice.workspace_id == workspace_id,
                    BusinessInvoice.vendor_id == vendor.id,
                    BusinessInvoice.id != invoice.id,
                    BusinessInvoice.invoice_date == inv_date,
                    BusinessInvoice.total == total,
                )
                .limit(1)
            )
            if inv_date and total
            else None
        )
        if near:
            result(
                "NEAR_DUPLICATE",
                False,
                f"Same vendor/date/amount as invoice {near.invoice_number}; investigate similarity.",
            )
    balance = None
    if po:
        consumed = session.scalar(
            select(func.coalesce(func.sum(FinancialCommitment.amount), 0)).where(
                FinancialCommitment.po_id == po.id,
                FinancialCommitment.status.in_(CONSUMING),
                FinancialCommitment.invoice_id != replace_invoice_id
                if replace_invoice_id
                else True,
            )
        )
        balance = po.authorized_gross - consumed
        if total is not None and total > 0 and currency == po.currency:
            result(
                "PO_BALANCE",
                total <= balance,
                f"Requested {currency} {total}; remaining {po.currency} {balance}; excess {max(total - balance, Decimal(0))}.",
                total,
                balance,
                failure="BLOCK",
            )
        for p in po_items:
            if p.id not in allocations:
                continue
            used = session.scalar(
                select(func.coalesce(func.sum(CommitmentAllocation.quantity), 0))
                .join(
                    FinancialCommitment,
                    CommitmentAllocation.commitment_id == FinancialCommitment.id,
                )
                .where(
                    FinancialCommitment.po_id == po.id,
                    FinancialCommitment.status.in_(CONSUMING),
                    FinancialCommitment.invoice_id != replace_invoice_id
                    if replace_invoice_id
                    else True,
                    CommitmentAllocation.po_item_id == p.id,
                )
            )
            result(
                f"QUANTITY_{p.line_number}",
                used + allocations[p.id] <= p.quantity,
                "Cumulative item quantity cannot exceed ordered quantity.",
                used + allocations[p.id],
                p.quantity,
                failure="BLOCK",
            )
    outcome = (
        "BLOCKED"
        if any(r["outcome"] == "BLOCK" for r in rules)
        else "NEEDS_REVIEW"
        if any(r["outcome"] == "REVIEW" for r in rules)
        else "VALIDATED"
    )
    if outcome == "VALIDATED" and replace_invoice_id and invoice and vendor and inv_number:
        invoice.identity_key = identity
        invoice.vendor_id = vendor.id
        invoice.invoice_number = inv_number
        invoice.invoice_date = inv_date
        invoice.currency = currency
        invoice.total = total
    summary = {
        "vendor": vendor.legal_name if vendor else None,
        "po_number": po.number if po else None,
        "currency": currency,
        "po_currency": po.currency if po else None,
        "requested": str(total) if total is not None else None,
        "available_before": str(balance) if balance is not None else None,
        "original_document_id": str(invoice.source_document_id) if invoice else None,
        "payment_executed": False,
    }
    return outcome, rules, summary, invoice, po, allocations
