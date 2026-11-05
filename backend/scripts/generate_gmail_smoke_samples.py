"""Generate synthetic Gmail smoke PDFs; never reads or modifies a database."""

import argparse
from datetime import date
from pathlib import Path

from scripts.generate_samples import invoice_pdf


def generate(output):
    output.mkdir(parents=True, exist_ok=False)
    common = {
        "vendor_name": "Mail Test Supplier (Synthetic)",
        "vendor_code": "MAIL-001",
        "vendor_tax_id": "SYNTHETIC-MAIL-001",
        "po": "MAIL-PO-001",
        "invoice_date": date.today().isoformat(),
    }
    cases = {
        "valid.pdf": {
            "number": "MAIL-LIVE-001",
            "quantity": "3",
            "subtotal": "60",
            "tax": "6",
            "total": "66",
        },
        "overbilling.pdf": {
            "number": "MAIL-LIVE-002",
            "quantity": "8",
            "subtotal": "160",
            "tax": "16",
            "total": "176",
        },
        "scanned.pdf": {
            "number": "MAIL-LIVE-003",
            "quantity": "1",
            "subtotal": "20",
            "tax": "2",
            "total": "22",
            "scanned": True,
        },
    }
    for name, fields in cases.items():
        (output / name).write_bytes(invoice_pdf(**common, **fields))
    print(f"Created {len(cases)} SYNTHETIC PDFs in {output}. No database or mailbox was accessed.")
    print(
        "Create MAIL-001 and MAIL-PO-001 in the UI first: USD 220 authorization, 10 PAPER-A4 units at 20 + 10% tax."
    )
    print(
        "Send valid.pdf first and wait for its decision; then overbilling.pdf. Resend the same valid.pdf bytes for exact replay."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("../.local/gmail-smoke"))
    generate(parser.parse_args().output)
