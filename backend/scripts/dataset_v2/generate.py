import hashlib
import random

from scripts.dataset_v2.catalogue import catalogue
from scripts.dataset_v2.common import DATA, PRIVATE, SEED, VERSION, digest, write_json
from scripts.dataset_v2.facts import make_invoice, scenario_groups
from scripts.dataset_v2.oracle import oracle_group
from scripts.dataset_v2.render import draw_pdf


def generate():
    if (DATA / "freeze.json").exists():
        raise RuntimeError("Dataset frozen. Refusing overwrite; use a new dataset version.")
    cat = catalogue()
    write_json(DATA / "procurement.json", cat)
    vendors = {v["id"]: v for v in cat["vendors"]}
    baseline = {}
    baselines = []
    for p in cat["purchase_orders"]:
        if p["status"] != "PARTIALLY_BILLED":
            continue
        facts = make_invoice(p, vendors[p["vendor_id"]], "BASE-" + p["number"], "2")
        facts["fields"]["invoice_date"] = "2026-02-01"
        pdf, _, _ = draw_pdf(facts, "D0")
        path = DATA / "baseline" / f"{p['number']}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
        baseline[p["id"]] = facts["fields"]["total"]
        baselines.append(
            {
                "file": str(path.relative_to(DATA)),
                "sha256": digest(path),
                "po_id": p["id"],
                "amount": facts["fields"]["total"],
                "quantity": "2",
            }
        )
    manifest = {
        "version": VERSION,
        "seed": SEED,
        "synthetic": True,
        "baseline": baselines,
        "documents": [],
        "scoring_policy": "independent-rational-v1",
    }
    all_answers = {}
    for split, count, scans in [("development", 80, 30), ("heldout", 40, 16)]:
        groups = scenario_groups(cat, split)
        flat = [d for g in groups for d in g]
        assert len(flat) == count
        excluded = {i for i, d in enumerate(flat) if d["scenario"] == "exact_replay"}
        scan_indices = set(
            random.Random(SEED + (split == "heldout")).sample(
                [i for i in range(count) if i not in excluded], scans
            )
        )
        answers = {}
        index = 0
        for group_index, group in enumerate(groups):
            group_name = f"{split}-group-{group_index:03}"
            expected = oracle_group(group, cat, baseline)
            layout = ("D" if split == "development" else "H") + str(
                group_index % (8 if split == "development" else 4)
            )
            first_pdf = None
            for step, (source, answer) in enumerate(zip(group, expected, strict=True)):
                case_id = hashlib.sha256(
                    f"{VERSION}/{split}/{group_index}/{step}".encode()
                ).hexdigest()[:16]
                facts = source["facts"]
                if source["scenario"] == "ambiguous_date":
                    facts["display_ambiguous_date"] = True
                if source["scenario"] == "ambiguous_po":
                    facts["display_ambiguous_po"] = True
                pdf, visible, scan_profile = draw_pdf(
                    facts,
                    layout,
                    index in scan_indices,
                    SEED + index + (1000 if split == "heldout" else 0),
                    step,
                )
                if source["scenario"] == "exact_replay" and step == 1:
                    pdf = first_pdf
                if step == 0:
                    first_pdf = pdf
                folder = "development/inputs" if split == "development" else "evaluation-inputs"
                path = DATA / folder / (case_id + ".pdf")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(pdf)
                entry = {
                    "id": case_id,
                    "split": split,
                    "group": group_name,
                    "order": step,
                    "file": str(path.relative_to(DATA)),
                    "sha256": digest(path),
                    "layout": layout,
                    "scanned": index in scan_indices,
                    "scan_profile": scan_profile,
                    "derivation_family": group_name,
                }
                manifest["documents"].append(entry)
                po = next((p for p in cat["purchase_orders"] if p["id"] == source["po_id"]), None)
                # Facts used by rendering are distinct from the independent expected policy answers.
                answers[case_id] = {
                    **answer,
                    "source_currency": po["currency"] if po else facts["fields"]["currency"],
                    "visible_values": visible,
                }
                index += 1
        path = (
            DATA / "development/answers.json" if split == "development" else PRIVATE / "oracle.json"
        )
        write_json(path, {"version": VERSION, "seed": SEED, "cases": answers})
        all_answers[split] = digest(path)
    write_json(DATA / "manifest.json", manifest)
    policy = {
        "version": "independent-rational-v1",
        "rounding": "ROUND_HALF_UP",
        "currency_minor_digits": {"USD": 2, "INR": 2, "EUR": 2, "GBP": 2, "JPY": 0, "KWD": 3},
        "decision_correctness": "strict; review on a gold-valid invoice is missed automation, not success",
        "false_validation": "VALIDATED when independent gold requires BLOCKED or NEEDS_REVIEW",
        "field_denominators": "present gold fields; missing-field abstentions separate; exact bytes deduplicated",
        "unsupported": "non-null output without valid source evidence; factual errors reported separately",
        "technical_failures": "included in attempted invoice denominator; no financial outcome fabricated",
    }
    write_json(PRIVATE / "scoring-policy.json", policy)
    write_json(
        DATA / "freeze.json",
        {
            "version": VERSION,
            "seed": SEED,
            "manifest_sha256": digest(DATA / "manifest.json"),
            "catalogue_sha256": digest(DATA / "procurement.json"),
            "answer_sha256": all_answers,
            "scoring_policy_sha256": digest(PRIVATE / "scoring-policy.json"),
            "generator_sha256": {
                p.name: digest(p)
                for p in sorted(__import__("pathlib").Path(__file__).parent.glob("*.py"))
                if p.name
                in [
                    "generate.py",
                    "facts.py",
                    "catalogue.py",
                    "oracle.py",
                    "render.py",
                    "common.py",
                ]
            },
        },
    )
    return {
        "vendors": len(cat["vendors"]),
        "purchase_orders": len(cat["purchase_orders"]),
        "documents": len(manifest["documents"]),
        "baseline_pdfs": len(baselines),
        "development": 80,
        "heldout": 40,
        "scanned": 46,
    }
