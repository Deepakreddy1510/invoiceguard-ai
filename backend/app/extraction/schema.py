from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None
    page: int | None
    quote: str | None


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: EvidenceValue
    quantity: EvidenceValue
    unit_price: EvidenceValue
    net: EvidenceValue
    tax_rate: EvidenceValue
    tax: EvidenceValue
    gross: EvidenceValue


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["INVOICE", "CREDIT_NOTE", "UNKNOWN"]
    vendor_name: EvidenceValue
    vendor_code: EvidenceValue
    tax_id: EvidenceValue
    invoice_number: EvidenceValue
    invoice_date: EvidenceValue
    po_number: EvidenceValue
    currency: EvidenceValue
    pricing_mode: EvidenceValue
    subtotal: EvidenceValue
    discount: EvidenceValue
    charges: EvidenceValue
    tax: EvidenceValue
    total: EvidenceValue
    items: list[LineItem] = Field(max_length=200)
    issues: list[str] = Field(max_length=100)


FIELDS = list(InvoiceExtraction.model_fields.keys())[1:-2]
EMPTY = {"value": None, "page": None, "quote": None}
