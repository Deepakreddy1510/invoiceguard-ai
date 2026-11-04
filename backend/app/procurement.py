"""Audited procurement mutations under the same lock as financial finalization."""

import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select

from app.audit import audit
from app.models import (
    BusinessInvoice,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
    PurchaseOrder,
    PurchaseOrderItem,
    Vendor,
)
from app.validation.engine import CURRENCY_UNITS


def canonical(value):
    return unicodedata.normalize("NFKC", value).strip().upper()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VendorInput(Input):
    legal_name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=40)
    tax_id: str | None = Field(default=None, max_length=80)
    status: Literal["APPROVED", "SUSPENDED", "INACTIVE"] = "APPROVED"

    @field_validator("code")
    @classmethod
    def code_format(cls, value):
        value = canonical(value)
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,39}", value):
            raise ValueError(
                "Use letters, digits, dot, underscore, slash or hyphen in vendor codes."
            )
        return value

    @field_validator("tax_id")
    @classmethod
    def tax_format(cls, value):
        value = canonical(value) if value else None
        return value or None


class VendorUpdate(VendorInput):
    version: int = Field(ge=1)


def bounded_decimal(value, fractional_digits):
    if not isinstance(value, (str, Decimal)) or not re.fullmatch(
        rf"\d{{1,14}}(?:\.\d{{1,{fractional_digits}}})?", str(value)
    ):
        raise ValueError(
            f"Use a nonnegative decimal string with at most 14 integer and {fractional_digits} fractional digits."
        )
    return Decimal(value)


def decimal_string(value):
    return bounded_decimal(value, 6)


class ItemInput(Input):
    sku: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    _numbers = field_validator("quantity", "unit_price", mode="before")(decimal_string)

    @field_validator("tax_rate", mode="before")
    @classmethod
    def rate_decimal(cls, value):
        return bounded_decimal(value, 8)

    @model_validator(mode="after")
    def amounts(self):
        if self.quantity <= 0 or self.tax_rate > 1:
            raise ValueError("Quantity must be positive and tax rate must be between zero and one.")
        return self


class POInput(Input):
    number: str = Field(min_length=1, max_length=60)
    vendor_id: UUID
    currency: Literal["USD", "INR", "EUR", "GBP", "JPY", "KWD"]
    status: Literal["OPEN", "PARTIALLY_BILLED", "CLOSED", "CANCELLED"] = "OPEN"
    issued_on: date
    valid_until: date
    billing_mode: Literal["ITEMIZED", "AMOUNT_BASED"]
    authorized_gross: Decimal
    items: list[ItemInput] = Field(default_factory=list, max_length=200)
    _gross = field_validator("authorized_gross", mode="before")(decimal_string)

    @field_validator("number")
    @classmethod
    def number_format(cls, value):
        value = canonical(value)
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,59}", value):
            raise ValueError("Use letters, digits, dot, underscore, slash or hyphen in PO numbers.")
        return value

    @model_validator(mode="after")
    def consistency(self):
        unit = CURRENCY_UNITS[self.currency]
        if self.authorized_gross <= 0 or self.authorized_gross != self.authorized_gross.quantize(
            unit
        ):
            raise ValueError("Authorization must be positive and respect currency minor units.")
        if self.valid_until < self.issued_on:
            raise ValueError("Valid-until date cannot precede issue date.")
        if self.billing_mode == "ITEMIZED" and not self.items:
            raise ValueError("An itemized PO requires at least one item.")
        if len({item.sku.casefold() for item in self.items}) != len(self.items):
            raise ValueError("SKUs must be unique within a purchase order.")
        if self.items and po_totals(self)["gross"] != self.authorized_gross:
            raise ValueError(
                "Authorized gross must equal the currency-rounded item subtotal plus tax."
            )
        return self


class POUpdate(POInput):
    version: int = Field(ge=1)


class Cancellation(Input):
    version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


def po_totals(data):
    unit = CURRENCY_UNITS[data.currency]
    with localcontext() as context:
        context.prec = 60
        net = sum(
            (
                (item.quantity * item.unit_price).quantize(unit, rounding=ROUND_HALF_UP)
                for item in data.items
            ),
            Decimal(0),
        )
        tax = sum(
            (
                (
                    (item.quantity * item.unit_price).quantize(unit, rounding=ROUND_HALF_UP)
                    * item.tax_rate
                ).quantize(unit, rounding=ROUND_HALF_UP)
                for item in data.items
            ),
            Decimal(0),
        )
    return {"subtotal": net, "tax": tax, "gross": net + tax}


def vendor_for(session, user, identifier):
    vendor = session.scalar(
        select(Vendor).where(Vendor.id == identifier, Vendor.workspace_id == user.workspace_id)
    )
    if not vendor:
        raise HTTPException(404, "Vendor not found in this workspace.")
    return vendor


def po_for(session, user, identifier):
    po = session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.id == identifier, PurchaseOrder.workspace_id == user.workspace_id
        )
    )
    if not po:
        raise HTTPException(404, "Purchase order not found in this workspace.")
    return po


def po_history(session, po):
    return bool(
        session.scalar(select(Decision.id).where(Decision.po_id == po.id).limit(1))
        or session.scalar(
            select(FinancialCommitment.id).where(FinancialCommitment.po_id == po.id).limit(1)
        )
    )


def vendor_view(session, vendor):
    count = session.scalar(
        select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor.id)
    )
    used = count > 0 or bool(
        session.scalar(
            select(BusinessInvoice.id).where(BusinessInvoice.vendor_id == vendor.id).limit(1)
        )
        or session.scalar(
            select(Decision.id)
            .join(ProcessingRun, Decision.run_id == ProcessingRun.id)
            .join(InvoiceDocument, ProcessingRun.document_id == InvoiceDocument.id)
            .where(
                InvoiceDocument.workspace_id == vendor.workspace_id,
                Decision.summary["vendor"].astext == vendor.legal_name,
            )
            .limit(1)
        )
    )
    return {
        "id": str(vendor.id),
        "legal_name": vendor.legal_name,
        "code": vendor.code,
        "tax_id": vendor.tax_id,
        "status": vendor.status,
        "version": vendor.version,
        "po_count": count,
        "identity_locked": used,
    }


def check_version(record, version):
    if record.version != version:
        raise HTTPException(409, "This record changed. Reload the current version before saving.")


def create_vendor(session, user, data):
    for existing in session.scalars(select(Vendor).where(Vendor.workspace_id == user.workspace_id)):
        if canonical(existing.code) == data.code:
            raise HTTPException(409, "A vendor with this code already exists in this workspace.")
        if data.tax_id and existing.tax_id and canonical(existing.tax_id) == data.tax_id:
            raise HTTPException(
                409,
                "This tax identifier already belongs to another vendor. Resolve identity before adding a duplicate.",
            )
    vendor = Vendor(workspace_id=user.workspace_id, **data.model_dump())
    session.add(vendor)
    session.flush()
    audit(
        session,
        user.workspace_id,
        user.subject,
        "VENDOR_CREATED",
        {"vendor": vendor_view(session, vendor)},
    )
    return vendor


def update_vendor(session, user, vendor, data):
    check_version(vendor, data.version)
    before = vendor_view(session, vendor)
    if before["identity_locked"] and any(
        getattr(vendor, key) != getattr(data, key) for key in ["code", "legal_name", "tax_id"]
    ):
        raise HTTPException(
            409,
            "Vendor identity is locked because procurement or invoices reference it. Deactivate it and create a distinct vendor instead.",
        )
    for other in session.scalars(
        select(Vendor).where(Vendor.workspace_id == user.workspace_id, Vendor.id != vendor.id)
    ):
        if canonical(other.code) == data.code or (
            data.tax_id and other.tax_id and canonical(other.tax_id) == data.tax_id
        ):
            raise HTTPException(409, "Vendor code or tax identifier conflicts with another vendor.")
    for key, value in data.model_dump(exclude={"version"}).items():
        setattr(vendor, key, value)
    vendor.version += 1
    audit(
        session,
        user.workspace_id,
        user.subject,
        "VENDOR_UPDATED",
        {"before": before, "after": vendor_view(session, vendor)},
    )
    return vendor


def delete_vendor(session, user, vendor, version):
    check_version(vendor, version)
    before = vendor_view(session, vendor)
    if before["identity_locked"]:
        raise HTTPException(
            409,
            "This vendor has dependent records. Deactivate it instead; history will be retained.",
        )
    session.delete(vendor)
    audit(session, user.workspace_id, user.subject, "VENDOR_DELETED", {"before": before})


def create_po(session, user, data):
    vendor_for(session, user, data.vendor_id)
    if session.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.workspace_id == user.workspace_id,
            func.upper(PurchaseOrder.number) == data.number,
        )
    ):
        raise HTTPException(
            409, "A purchase order with this number already exists in this workspace."
        )
    if data.status == "PARTIALLY_BILLED":
        raise HTTPException(
            422,
            "Create an open PO and process the historical invoice; status alone cannot establish billed capacity.",
        )
    po = PurchaseOrder(workspace_id=user.workspace_id, **data.model_dump(exclude={"items"}))
    session.add(po)
    session.flush()
    replace_items(session, po, data.items)
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PURCHASE_ORDER_CREATED",
        {
            "po_id": str(po.id),
            "data": data.model_dump(mode="json"),
            "totals": {k: str(v) for k, v in po_totals(data).items()},
        },
    )
    return po


def replace_items(session, po, items):
    for old in session.scalars(
        select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
    ).all():
        session.delete(old)
    session.flush()
    for index, item in enumerate(items, 1):
        session.add(PurchaseOrderItem(po_id=po.id, line_number=index, **item.model_dump()))
    session.flush()


def update_po(session, user, po, data):
    check_version(po, data.version)
    if po_history(session, po):
        raise HTTPException(
            409,
            "Financial history locks PO authorization, identity, dates and items. Retain this PO and create a new authorization, or cancel it explicitly.",
        )
    vendor_for(session, user, data.vendor_id)
    if data.status == "PARTIALLY_BILLED":
        raise HTTPException(
            422,
            "Process actual historical invoices instead of setting an unrecorded billed status.",
        )
    if session.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.workspace_id == user.workspace_id,
            PurchaseOrder.id != po.id,
            func.upper(PurchaseOrder.number) == data.number,
        )
    ):
        raise HTTPException(409, "This purchase-order number already exists.")
    before = {
        key: str(getattr(po, key))
        for key in [
            "number",
            "vendor_id",
            "currency",
            "status",
            "authorized_gross",
            "issued_on",
            "valid_until",
            "billing_mode",
        ]
    }
    for key, value in data.model_dump(exclude={"version", "items"}).items():
        setattr(po, key, value)
    po.version += 1
    replace_items(session, po, data.items)
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PURCHASE_ORDER_UPDATED",
        {"po_id": str(po.id), "before": before, "after": data.model_dump(mode="json")},
    )
    return po


def delete_po(session, user, po, version):
    check_version(po, version)
    if po_history(session, po):
        raise HTTPException(
            409, "This purchase order has financial history. Cancel it instead of deleting it."
        )
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PURCHASE_ORDER_DELETED",
        {"po_id": str(po.id), "number": po.number},
    )
    for item in session.scalars(
        select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
    ).all():
        session.delete(item)
    session.flush()
    session.delete(po)
