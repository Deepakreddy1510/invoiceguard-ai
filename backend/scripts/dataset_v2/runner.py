"""Oracle-aware controller; application child receives input PDFs only."""

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import (
    BusinessInvoice,
    CommitmentAllocation,
    Decision,
    FinancialCommitment,
    InvoiceDocument,
    ProcessingRun,
    RunEvent,
)
from scripts.dataset_v2.common import (
    DATA,
    PRIVATE,
    ROOT,
    VERSION,
    digest,
    load,
    source_hashes,
    write_json,
)
from scripts.dataset_v2.isolation import DatabasePool, child_environment
from scripts.dataset_v2.scoring import aggregate, field_scores
from scripts.dataset_v2.seed import seed_catalogue


def invoke(mode, url, storage, provider, pdf=None):
    with tempfile.NamedTemporaryFile(suffix=".json", dir=storage, delete=False) as f:
        output = Path(f.name)
    command = [
        sys.executable,
        "-m",
        "scripts.dataset_v2.child",
        "--mode",
        mode,
        "--output",
        str(output),
    ]
    if pdf:
        command += ["--pdf", str(pdf)]
    try:
        process = subprocess.run(
            command,
            cwd=ROOT / "backend",
            env=child_environment(url, storage, provider),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if process.returncode:
            raise RuntimeError(
                "Input process failed: "
                + (process.stderr.splitlines()[-1][:150] if process.stderr else "no error detail")
            )
        return load(output) if mode != "migrate" else {}
    finally:
        output.unlink(missing_ok=True)


def gold_fields(answer):
    # Assumed verified facts for engine isolation, explicitly NOT extraction evidence.
    def wrap(value):
        return {
            "value": value,
            "page": None,
            "quote": None,
            "verified": value is not None,
            "method": "GOLD_ORACLE",
        }

    facts = answer["facts"]
    return {
        "provider": "GOLD_ORACLE",
        "fields": {
            "document_type": facts["document_type"],
            **{k: wrap(v) for k, v in facts["fields"].items()},
            "items": [{k: wrap(v) for k, v in i.items()} for i in facts["items"]],
            "issues": [],
        },
    }


def gold_submit(engine, entry, answer):
    from app.worker.main import finalize

    with Session(engine) as session, session.begin():
        doc = session.scalar(
            select(InvoiceDocument).where(InvoiceDocument.sha256 == entry["sha256"])
        )
        if doc:
            run = session.scalar(select(ProcessingRun).where(ProcessingRun.document_id == doc.id))
            return {"run_id": str(run.id), "replayed": True}
        doc = InvoiceDocument(
            workspace_id=UUID("00000000-0000-0000-0000-000000000001"),
            sha256=entry["sha256"],
            storage_key=str(uuid4()) + ".pdf",
            byte_size=(DATA / entry["file"]).stat().st_size,
            page_count=1,
        )
        session.add(doc)
        session.flush()
        run = ProcessingRun(
            document_id=doc.id,
            status="RUNNING",
            attempt=1,
            lease_token=uuid4(),
            extraction=gold_fields(answer),
        )
        session.add(run)
        session.flush()
        finalize(session, run.id, run.lease_token)
        return {"run_id": str(run.id), "replayed": False}


def observation(engine, receipt, cat):
    with Session(engine) as session:
        run = session.get(ProcessingRun, UUID(receipt["run_id"]))
        decision = session.scalar(select(Decision).where(Decision.run_id == run.id))
        invoice = (
            session.get(BusinessInvoice, decision.invoice_id)
            if decision and decision.invoice_id
            else None
        )
        names = [
            v["id"]
            for v in cat["vendors"]
            if decision and v["legal_name"] == decision.summary.get("vendor")
        ]
        return {
            "status": run.status,
            "error": run.error,
            "extraction": run.extraction,
            "pages": run.pages,
            "run_id": str(run.id),
            "event_count": session.scalar(
                select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run.id)
            ),
            "actual_decision": decision.outcome if decision else None,
            "actual_vendor": str(invoice.vendor_id)
            if invoice
            else names[0]
            if len(names) == 1
            else None,
            "actual_po": str(decision.po_id) if decision and decision.po_id else None,
            "rules": decision.rules if decision else [],
        }


def snapshot(engine, cat):
    with Session(engine) as s:
        commitments = s.scalars(select(FinancialCommitment)).all()
        allocations = s.scalars(select(CommitmentAllocation)).all()
        consumption = defaultdict(Decimal)
        for c in commitments:
            if c.status in ["RESERVED", "HELD", "SETTLED"]:
                consumption[str(c.po_id)] += c.amount
        return {
            "ids": {str(c.id) for c in commitments},
            "commitments": {
                str(c.id): {"amount": str(c.amount), "po_id": str(c.po_id), "currency": c.currency}
                for c in commitments
            },
            "allocations": {
                str(a.commitment_id) + "/" + str(a.po_item_id): str(a.quantity) for a in allocations
            },
            "balances": {
                p["id"]: str(Decimal(p["authorized_gross"]) - consumption[p["id"]])
                for p in cat["purchase_orders"]
            },
        }


def compare_financial(result, answer, observed, before, after, receipt):
    result.update(
        actual_decision=observed["actual_decision"],
        run_id=observed["run_id"],
        event_count=observed["event_count"],
    )
    result["vendor_correct"] = observed["actual_vendor"] == answer["vendor_id"]
    result["actual_vendor"] = observed["actual_vendor"]
    result["po_correct"] = observed["actual_po"] == answer["po_id"]
    result["actual_po"] = observed["actual_po"]
    new = after["ids"] - before["ids"]
    delta = sum((Decimal(after["commitments"][i]["amount"]) for i in new), Decimal(0))
    result["actual_commitment_delta"] = str(delta)
    result["commitment_correct"] = (
        delta == Decimal(answer["commitment_delta"])
        and len(new) == (1 if Decimal(answer["commitment_delta"]) > 0 else 0)
        and all(after["commitments"][i]["po_id"] == answer["po_id"] for i in new)
    )
    alloc = {
        k.split("/")[1]: v
        for k, v in after["allocations"].items()
        if k not in before["allocations"]
    }
    result["allocations_correct"] = {k: Decimal(v) for k, v in alloc.items()} == {
        k: Decimal(v) for k, v in answer["allocations_delta"].items()
    }
    po = answer["po_id"]
    for key, snap in [("balance_before", before), ("balance_after", after)]:
        actual = snap["balances"].get(po) if po else None
        result["actual_" + key] = actual
        result[key + "_correct"] = (actual is None and answer[key] is None) or (
            actual is not None
            and answer[key] is not None
            and Decimal(actual) == Decimal(answer[key])
        )
    result["replay_correct"] = receipt["replayed"] == answer["replay"]
    actual_rules = {r["rule_id"]: r["outcome"] for r in observed["rules"]}
    result["rule_checks"] = len(answer["expected_rules"])
    result["correct_rules"] = sum(
        actual_rules.get(k) == v for k, v in answer["expected_rules"].items()
    )
    result["rule_mismatches"] = {
        k: {"expected": v, "actual": actual_rules.get(k)}
        for k, v in answer["expected_rules"].items()
        if actual_rules.get(k) != v
    }


def evaluate(mode, split, provider, admin_url, report_path):
    if provider == "gemini":
        from app.config import get_settings

        if not get_settings().gemini_api_key:
            raise RuntimeError(
                "Live Gemini explicitly requested but no key configured. Refusing to label fallback as Gemini."
            )
    from scripts.dataset_v2.integrity import validate_answers, validate_public

    validate_public()
    validate_answers(split)
    manifest = load(DATA / "manifest.json")
    cat = load(DATA / "procurement.json")
    answer_path = (
        DATA / "development/answers.json" if split == "development" else PRIVATE / "oracle.json"
    )
    answers = load(answer_path)["cases"]
    entries = [e for e in manifest["documents"] if e["split"] == split]
    groups = defaultdict(list)
    for entry in entries:
        groups[entry["group"]].append(entry)
    results = []
    hashes_before = source_hashes()
    created = []
    with tempfile.TemporaryDirectory(prefix="ig-eval-v2-") as temp, DatabasePool(admin_url) as pool:
        storage = Path(temp)
        template, url = pool.create()
        created.append(template)
        invoke("migrate", url, storage, "fallback")
        engine = create_engine(url)
        seed_catalogue(engine, cat)
        # Actual worker-processed baseline, not fabricated OCR history or direct ledger rows.
        for b in manifest["baseline"]:
            receipt = invoke("worker", url, storage, "fallback", DATA / b["file"])
            obs = observation(engine, receipt, cat)
            if obs["actual_decision"] != "VALIDATED":
                raise RuntimeError("Baseline did not validate: " + b["file"])
        base = snapshot(engine, cat)
        for b in manifest["baseline"]:
            expected = Decimal(
                next(p["authorized_gross"] for p in cat["purchase_orders"] if p["id"] == b["po_id"])
            ) - Decimal(b["amount"])
            if Decimal(base["balances"][b["po_id"]]) != expected:
                raise RuntimeError("Incorrect baseline commitment")
        engine.dispose()
        for index, (_group, documents) in enumerate(groups.items()):
            name, group_url = pool.create(template)
            created.append(name)
            engine = create_engine(group_url)
            try:
                for entry in documents:
                    answer = answers[entry["id"]]
                    result = {
                        **{k: entry[k] for k in ["id", "sha256", "layout", "scanned", "group"]},
                        "currency": answer["source_currency"],
                        "scenario": answer["scenario"],
                        "expected_decision": answer["expected_decision"],
                    }
                    before = snapshot(engine, cat)
                    try:
                        if mode == "extraction":
                            observed = invoke(
                                "extraction", group_url, storage, provider, DATA / entry["file"]
                            )
                        else:
                            receipt = (
                                gold_submit(engine, entry, answer)
                                if mode == "gold"
                                else invoke(
                                    "worker", group_url, storage, provider, DATA / entry["file"]
                                )
                            )
                            observed = observation(engine, receipt, cat)
                            if observed["status"] != "SUCCEEDED":
                                raise RuntimeError(
                                    "Worker technical failure: " + str(observed["error"])
                                )
                            compare_financial(
                                result, answer, observed, before, snapshot(engine, cat), receipt
                            )
                        extraction = observed["extraction"]
                        result["actual_provider"] = extraction["provider"]
                        if (
                            provider == "gemini"
                            and extraction["provider"] != "GEMINI"
                            and mode != "gold"
                        ):
                            result["provider_fallback"] = True
                        if mode != "gold":
                            result["field_counts"], result["field_details"] = field_scores(
                                answer, extraction, observed["pages"]
                            )
                    except Exception as exc:
                        result["technical_failure"] = type(exc).__name__ + ": " + str(exc)[:200]
                        if mode != "gold":
                            result["field_counts"], result["field_details"] = field_scores(
                                answer, None, []
                            )
                    results.append(result)
            finally:
                engine.dispose()
                pool.drop(name)
            print(f"{mode}/{split}: {index + 1}/{len(groups)} isolated groups complete", flush=True)
        pool.drop(template)
        if pool.owned:
            raise RuntimeError("Evaluation database cleanup incomplete")
    report = aggregate(results, mode, "GOLD_ORACLE" if mode == "gold" else provider, split)
    import importlib.metadata

    report["provenance"] = {
        "evaluator_sources": {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted((ROOT / "backend/scripts/dataset_v2").glob("*.py"))
        },
        "dataset_version": VERSION,
        "manifest_sha256": digest(DATA / "manifest.json"),
        "oracle_sha256": digest(answer_path),
        "scoring_policy_sha256": digest(PRIVATE / "scoring-policy.json"),
        "application_sources": hashes_before,
        "application_source_sha256": hashlib.sha256(
            json.dumps(hashes_before, sort_keys=True).encode()
        ).hexdigest(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "uncommitted_implementation": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "seed": manifest["seed"],
        "python": platform.python_version(),
        "pymupdf": importlib.metadata.version("pymupdf"),
        "tesseract": subprocess.check_output(["tesseract", "--version"], text=True).splitlines()[0],
        "evaluation_time_utc": datetime.now(timezone.utc).isoformat(),
        "ocr_thread_limit": 1,
        "business_date_policy": "invoice dates anchored in 2026; runtime business date recorded, not frozen",
        "runtime_business_date": datetime.now().date().isoformat(),
    }
    report["isolation"] = {
        "databases_created": len(created),
        "database_names": created,
        "databases_remaining": 0,
        "baseline_worker_invoices": 8,
        "production_sources_unchanged": source_hashes() == hashes_before,
    }
    report["live_gemini_executed"] = provider == "gemini" and mode != "gold"
    write_json(report_path, report)
    return {
        k: report[k]
        for k in [
            "mode",
            "split",
            "provider",
            "counts",
            "field_correctness",
            "decision_correctness",
            "review_rate",
            "isolation",
        ]
    }
