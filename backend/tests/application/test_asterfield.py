"""Presentation data is separate from the frozen extraction evaluation corpus."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from scripts.dataset_v2.isolation import DatabasePool, child_environment
from scripts.dataset_v2.runner import invoke
from scripts.install_asterfield_demo import cases, catalogue, generate


def test_realistic_catalogue_and_scoped_assets(tmp_path):
    catalog, manifest = generate(tmp_path)
    assert len(catalog["vendors"]) == 18
    assert len(catalog["purchase_orders"]) == 36
    assert len({v["code"] for v in catalog["vendors"]}) == 18
    assert {v["status"] for v in catalog["vendors"]} == {"APPROVED", "SUSPENDED", "INACTIVE"}
    assert len(manifest) == 21
    assert {d["medium"] for d in manifest} == {"digital", "scanned", "photographed"}
    assert len({d["layout"] for d in manifest}) == 3
    assert {d["expected"] for d in manifest} == {"VALIDATED", "NEEDS_REVIEW", "BLOCKED"}
    assert all(v["tax_id"].startswith("FICTIONAL-") for v in catalog["vendors"])
    first = {d["file"]: d["sha256"] for d in manifest}
    assert first == {d["file"]: d["sha256"] for d in generate(tmp_path)[1]}
    assert catalog == catalogue()


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["file"])
def test_real_invoice_files_have_correct_medium_and_hash(case):
    root = Path(__file__).parents[2] / "demo/asterfield-v1"
    manifest = json.loads((root / "manifest.json").read_text())
    record = next(d for d in manifest["documents"] if d["file"] == case["file"])
    pdf = (root / case["file"]).read_bytes()
    assert hashlib.sha256(pdf).hexdigest() == record["sha256"]
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) == 1
        text = doc[0].get_text()
        if case.get("scan") or case.get("photo"):
            assert not text.strip() and doc[0].get_images()
        else:
            assert "Sample company data" in text
            assert case["number"] in text


def test_actual_worker_decisions_balances_reinstallation_and_legacy_preservation(
    database, tmp_path
):
    # Only creates/drops DBs owned by this invocation; never accesses the user's demo.
    base = database.url.set(database="postgres").render_as_string(hide_password=False)
    with DatabasePool(base) as pool:
        _, url = pool.create()
        invoke("migrate", url, tmp_path, "fallback")
        env = child_environment(url, tmp_path, "fallback")
        probe = """
import json
from sqlalchemy import select,func
from app.db import SessionLocal
from app.seed import seed
from app.models import Workspace,Vendor,PurchaseOrder,ProcessingRun,FinancialCommitment,RunEvent,AuditEvent
from scripts.install_asterfield_demo import install
with SessionLocal.begin() as s: seed(s)
def counts():
    with SessionLocal() as s:
        return [s.scalar(select(func.count()).select_from(m)) for m in [Workspace,Vendor,PurchaseOrder,ProcessingRun,FinancialCommitment,RunEvent,AuditEvent]]
before=counts()
first=install(); after=counts(); second=install()
assert before[1:3]==[3,4]
assert after[1:3]==[21,40]
assert after==counts(), (after,counts())
assert first==second
assert first['outcomes']=={'VALIDATED':14,'BLOCKED':6,'NEEDS_REVIEW':1}
assert all(r['actual']==r['expected'] for r in first['results'])
with SessionLocal() as s:
    from app.config import DEMO_WORKSPACE_ID
    assert s.scalar(select(func.count()).select_from(Vendor).where(Vendor.workspace_id==DEMO_WORKSPACE_ID))==3
    assert s.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.workspace_id==DEMO_WORKSPACE_ID))==4
    from app.models import InvoiceDocument
    assert s.scalar(select(func.count()).select_from(InvoiceDocument).where(InvoiceDocument.workspace_id==DEMO_WORKSPACE_ID))==0
print(json.dumps(first))
"""
        result = subprocess.run(
            [sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, result.stdout + result.stderr
