import pymupdf

from app.extraction.pdf import read_pdf
from app.extraction.pipeline import structure


def table_pdf():
    doc = pymupdf.open()
    page = doc.new_page(width=900, height=700)
    headers = [
        "INVOICE",
        "Vendor: Northstar Office Supplies (Synthetic)",
        "Vendor code: SYN-001",
        "Tax id: SYNTHETIC-TAX-1",
        "Invoice number: NEW-TABLE-2026",
        "Invoice date: 15 Jun 2026",
        "Purchase order: PO-2026-001",
        "Currency: USD",
        "Pricing: TAX_EXCLUSIVE",
        "Subtotal: 200.00",
        "Discount: 0.00",
        "Charges: 0.00",
        "Tax: 20.00",
        "Grand total: 220.00",
    ]
    for n, line in enumerate(headers):
        page.insert_text((35, 35 + n * 24), line, fontsize=10)
    xs = [35, 220, 300, 420, 530, 640, 740]
    for x, text in zip(
        xs, ["SKU", "Qty", "Unit price", "Net", "Rate", "Tax", "Gross"], strict=True
    ):
        page.insert_text((x, 420), text, fontsize=10)
    for x, text in zip(
        xs, ["PAPER-A4", "10", "20.00", "200.00", "10%", "20.00", "220.00"], strict=True
    ):
        page.insert_text((x, 455), text, fontsize=10)
    result = doc.tobytes()
    doc.close()
    return result


def test_generic_table_date_percentage_and_source_evidence(tmp_path):
    path = tmp_path / "brand-new-layout.pdf"
    path.write_bytes(table_pdf())
    pages = read_pdf(str(path))["pages"]
    fields = structure(pages, "doc")["fields"]
    assert fields["invoice_date"]["value"] == "2026-06-15" and fields["invoice_date"]["verified"]
    assert len(fields["items"]) == 1
    assert fields["items"][0]["quantity"]["value"] == "10"
    assert fields["items"][0]["tax_rate"]["value"] == "0.1"
    assert all(v["verified"] for v in fields["items"][0].values()), fields
