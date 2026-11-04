"""Bounded CSV preview and atomic commit, using the ordinary procurement validators."""

import csv
import hashlib
from datetime import date
from io import StringIO
from typing import Annotated, Literal

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select

from app.audit import audit, financial_lock
from app.auth import Reviewer
from app.models import ProcurementImport, PurchaseOrder, Vendor
from app.procurement import POInput, VendorInput, canonical, create_po, create_vendor, po_totals
from app.workflow_api import DB

router = APIRouter(prefix="/api/v1/procurement/imports")
Kind = Literal["vendors", "purchase-orders"]
VENDOR_COLUMNS = ["legal_name", "code", "tax_id", "status"]
PO_COLUMNS = [
    "number",
    "vendor_code",
    "currency",
    "status",
    "issued_on",
    "valid_until",
    "billing_mode",
    "authorized_gross",
    "sku",
    "description",
    "quantity",
    "unit_price",
    "tax_rate",
]


def read_csv(payload, kind):
    if not payload or len(payload) > 256 * 1024:
        raise HTTPException(413, "Choose a nonempty UTF-8 CSV up to 256 KiB.")
    try:
        reader = csv.DictReader(StringIO(payload.decode("utf-8-sig")), strict=True)
        expected = VENDOR_COLUMNS if kind == "vendors" else PO_COLUMNS
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(expected)
            or set(reader.fieldnames) != set(expected)
        ):
            raise HTTPException(422, "CSV headers must match the downloadable template exactly.")
        rows = []
        for row in reader:
            if len(rows) >= 500:
                raise HTTPException(422, "Import at most 500 rows at a time.")
            if None in row or any(value is None for value in row.values()):
                raise HTTPException(422, "CSV row has the wrong number of columns.")
            if any(value.strip().startswith(("=", "+", "-", "@")) for value in row.values()):
                raise HTTPException(
                    422, "Spreadsheet formulas are not accepted. Use literal values only."
                )
            rows.append({k: v.strip() for k, v in row.items()})
        if not rows:
            raise HTTPException(422, "CSV contains no data rows.")
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise HTTPException(422, "CSV must be valid UTF-8 with well-formed quoted fields.") from exc


def prepare(session, user, payload, kind):
    rows = read_csv(payload, kind)
    errors = []
    records = []
    locations = []

    def error(row, message):
        errors.append({"row": row, "message": message})

    if kind == "vendors":
        existing = session.scalars(
            select(Vendor).where(Vendor.workspace_id == user.workspace_id)
        ).all()
        codes = {canonical(v.code) for v in existing}
        taxes = {canonical(v.tax_id) for v in existing if v.tax_id}
        for index, row in enumerate(rows, 2):
            try:
                data = VendorInput.model_validate({**row, "tax_id": row["tax_id"] or None})
                if data.code in codes or (data.tax_id and data.tax_id in taxes):
                    error(
                        index,
                        "Vendor code or tax identifier is duplicated in this workspace or CSV.",
                    )
                    continue
                codes.add(data.code)
                if data.tax_id:
                    taxes.add(data.tax_id)
                records.append(data)
                locations.append(index)
            except ValidationError as exc:
                for item in exc.errors(include_input=False):
                    error(index, " / ".join(map(str, item["loc"])) + ": " + item["msg"])
    else:
        groups = {}
        for index, row in enumerate(rows, 2):
            groups.setdefault(canonical(row["number"]), []).append((index, row))
        for number, entries in groups.items():
            index, first = entries[0]
            try:
                header = {key: first[key] for key in PO_COLUMNS[:8]}
                if any(any(row[key] != first[key] for key in PO_COLUMNS[:8]) for _, row in entries):
                    error(index, "Repeated PO rows must have identical header values.")
                    continue
                vendor = session.scalar(
                    select(Vendor).where(
                        Vendor.workspace_id == user.workspace_id,
                        func.upper(Vendor.code) == canonical(header.pop("vendor_code")),
                    )
                )
                if not vendor:
                    error(
                        index, "Vendor code does not exist in this workspace. Import vendors first."
                    )
                    continue
                if session.scalar(
                    select(PurchaseOrder.id).where(
                        PurchaseOrder.workspace_id == user.workspace_id,
                        func.upper(PurchaseOrder.number) == number,
                    )
                ):
                    error(index, "Purchase-order number already exists in this workspace.")
                    continue
                items = []
                item_rows = []
                for row_index, row in entries:
                    fields = {key: row[key] for key in PO_COLUMNS[8:]}
                    if any(fields.values()):
                        items.append(fields)
                        item_rows.append(row_index)
                    elif len(entries) > 1:
                        error(row_index, "Do not repeat an empty item row.")
                data = POInput.model_validate({**header, "vendor_id": vendor.id, "items": items})
                if data.status == "PARTIALLY_BILLED":
                    error(
                        index,
                        "Import an OPEN PO and process the historical invoice instead of inventing a billed balance.",
                    )
                    continue
                records.append(data)
                locations.append(index)
            except ValidationError as exc:
                for item in exc.errors(include_input=False):
                    location = item["loc"]
                    row_number = (
                        item_rows[location[1]]
                        if len(location) > 1
                        and location[0] == "items"
                        and isinstance(location[1], int)
                        else index
                    )
                    error(row_number, " / ".join(map(str, location)) + ": " + item["msg"])
    return {
        "valid": not errors,
        "kind": kind,
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "row_count": len(rows),
        "record_count": len(records),
        "errors": errors,
        "records": [
            {
                "row": row,
                "data": record.model_dump(mode="json"),
                **(
                    {"totals": {k: str(v) for k, v in po_totals(record).items()}}
                    if kind == "purchase-orders"
                    else {}
                ),
            }
            for row, record in zip(locations, records, strict=True)
        ],
    }, records


@router.get("/templates/{kind}.csv")
def template(kind: Kind, user: Reviewer):
    columns = VENDOR_COLUMNS if kind == "vendors" else PO_COLUMNS
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    if kind == "vendors":
        writer.writerow(
            ["Example Supplier (Synthetic)", "MY-V001", "SYNTHETIC-MY-TAX-001", "APPROVED"]
        )
    else:
        writer.writerow(
            [
                "MY-PO-001",
                "MY-V001",
                "USD",
                "OPEN",
                f"{date.today().year}-01-01",
                f"{date.today().year}-12-31",
                "ITEMIZED",
                "220.00",
                "PAPER-A4",
                "Synthetic paper cartons",
                "10",
                "20",
                "0.10",
            ]
        )
        writer.writerow(
            [
                "MY-PO-002",
                "MY-V001",
                "USD",
                "OPEN",
                f"{date.today().year}-01-01",
                f"{date.today().year}-12-31",
                "AMOUNT_BASED",
                "1000.00",
                "",
                "",
                "",
                "",
                "",
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{kind}-template.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/preview")
def preview(session: DB, user: Reviewer, kind: Kind, file: Annotated[UploadFile, File()]):
    result, _ = prepare(session, user, file.file.read(256 * 1024 + 1), kind)
    return result


@router.post("/commit")
def commit(
    session: DB,
    user: Reviewer,
    kind: Kind,
    file: Annotated[UploadFile, File()],
    idempotency_key: str = Header(min_length=1, max_length=100),
):
    payload = file.file.read(256 * 1024 + 1)
    digest = hashlib.sha256(payload).hexdigest()
    financial_lock(session, user.workspace_id)
    previous = session.scalar(
        select(ProcurementImport).where(
            ProcurementImport.workspace_id == user.workspace_id,
            ProcurementImport.idempotency_key == idempotency_key,
        )
    )
    if previous:
        if previous.sha256 != digest or previous.kind != kind:
            raise HTTPException(
                409, "Import idempotency key belongs to a different file or import type."
            )
        return {
            "import_id": str(previous.id),
            "row_count": previous.row_count,
            "record_count": previous.record_count,
            "replayed": True,
        }
    result, records = prepare(session, user, payload, kind)
    if not result["valid"]:
        raise HTTPException(
            422,
            {"message": "Import rejected. No records were created.", "errors": result["errors"]},
        )
    for record in records:
        (create_vendor if kind == "vendors" else create_po)(session, user, record)
    receipt = ProcurementImport(
        workspace_id=user.workspace_id,
        actor=user.subject,
        kind=kind,
        sha256=digest,
        idempotency_key=idempotency_key,
        record_count=len(records),
        row_count=result["row_count"],
    )
    session.add(receipt)
    session.flush()
    audit(
        session,
        user.workspace_id,
        user.subject,
        "PROCUREMENT_IMPORTED",
        {
            "import_id": str(receipt.id),
            "kind": kind,
            "sha256": digest,
            "row_count": receipt.row_count,
            "record_count": receipt.record_count,
        },
    )
    response = {
        "import_id": str(receipt.id),
        "record_count": receipt.record_count,
        "row_count": receipt.row_count,
        "replayed": False,
    }
    session.commit()
    return response
