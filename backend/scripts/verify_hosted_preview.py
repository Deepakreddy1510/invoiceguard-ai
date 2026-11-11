"""Verify a real deployment; never provisions resources or executes payments.

Set INVOICEGUARD_SMOKE_TOKEN securely to a reviewer access token for --workflow.
Run --verify-receipt again after restarting web/worker to verify persisted history.
A local-mode flag exists solely for testing this verifier on the synthetic demo.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from scripts.seed_workspace import document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="Actual provider-assigned HTTPS origin")
    parser.add_argument("--workflow", action="store_true")
    parser.add_argument("--workspace", type=UUID, help="Authorized synthetic workspace UUID")
    parser.add_argument("--include-overbilling", action="store_true")
    parser.add_argument("--include-ocr", action="store_true")
    parser.add_argument("--verify-receipt", action="store_true")
    parser.add_argument("--receipt", type=Path, default=Path("../.local/hosted-smoke.json"))
    parser.add_argument("--local", action="store_true", help="Internal verifier testing only")
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    if (
        origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in ["", "/"]
    ):
        parser.error("Use an origin without credentials, path, query or fragment.")
    local = args.local and origin.hostname in ["127.0.0.1", "localhost"]
    if origin.scheme != "https" and not (local and origin.scheme == "http"):
        parser.error("A deployed preview must use HTTPS.")
    token = os.environ.get("INVOICEGUARD_SMOKE_TOKEN")
    if (args.workflow or args.verify_receipt) and not (token or local):
        parser.error(
            "Set INVOICEGUARD_SMOKE_TOKEN securely; do not pass tokens on the command line."
        )
    headers = {"Authorization": "Bearer " + token} if token else {}
    if args.verify_receipt and not args.workspace:
        args.workspace = UUID(json.loads(args.receipt.read_text())["workspace_id"])
    if args.workspace:
        headers["X-Workspace-ID"] = str(args.workspace)
    receipt = {}
    with (
        httpx.Client(base_url=args.origin.rstrip("/"), timeout=60) as anonymous,
        httpx.Client(base_url=args.origin.rstrip("/"), headers=headers, timeout=60) as client,
    ):

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(
                    f"{method} {path} returned {response.status_code}; check provider logs privately."
                )
            return response

        root = anonymous.get("/")
        if root.status_code != 200 or '<div id="root"' not in root.text:
            raise RuntimeError("Compiled React entry page did not load.")
        if anonymous.get("/api/v1/health/ready").status_code != 200:
            raise RuntimeError("Application database is not ready.")
        config = anonymous.get("/api/v1/config")
        if config.status_code != 200 or (not local and config.json()["auth_mode"] != "supabase"):
            raise RuntimeError("Hosted Supabase configuration is missing.")
        if not local:
            for path in ["/api/v1/dashboard", "/api/v1/reviews", "/api/v1/audit-events"]:
                if anonymous.get(path).status_code != 401:
                    raise RuntimeError("Anonymous data access was not denied.")
        print("React entry, database readiness and authentication guard checks passed.", flush=True)
        if args.workflow:
            me = request("GET", "/api/v1/me").json()
            catalogue = json.loads(
                (Path(__file__).parents[1] / "demo/procurement.json").read_text()
            )
            po = catalogue["purchase_orders"][0]
            vendor = next(v for v in catalogue["vendors"] if v["id"] == po["vendor_id"])
            marker = "HTTPS-SMOKE-" + uuid4().hex[:12].upper()
            receipt = {
                "origin": args.origin.rstrip("/"),
                "workspace_id": me["workspace_id"],
                "runs": [],
            }
            scenarios = [
                ("fresh-invoice", "VALIDATED", "1", False, False),
                ("missing-number", "NEEDS_REVIEW", "2", True, False),
            ]
            if args.include_ocr:
                scenarios.append(("scanned-invoice", "VALIDATED", "3", False, True))
            if args.include_overbilling:
                scenarios.append(("overbilling", "BLOCKED", "1000", False, False))
            for label, expected, quantity, missing, scanned in scenarios:
                pdf = document(
                    po, vendor, marker + "-" + label, quantity, missing=missing, scanned=scanned
                )
                submission = request(
                    "POST",
                    "/api/v1/documents",
                    files={"file": (marker + ".pdf", pdf, "application/pdf")},
                ).json()
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    detail = request("GET", "/api/v1/runs/" + submission["run_id"]).json()
                    if detail["status"] in ["SUCCEEDED", "FAILED"]:
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError(
                        "Worker timed out; check heartbeat and queue without resetting the database."
                    )
                if detail["status"] != "SUCCEEDED" or detail["outcome"] != expected:
                    raise RuntimeError(
                        f"{label}: expected {expected}, observed {detail['status']}/{detail['outcome']}; inspect its source and current PO capacity. Do not alter rules to force a pass."
                    )
                if not detail["events"] or not detail["decision"]:
                    raise RuntimeError("Completed run is missing persisted decision/events.")
                source_path = "/api/v1/documents/" + submission["document_id"] + "/content"
                if request("GET", source_path).content != pdf:
                    raise RuntimeError("Stored PDF bytes differ from the uploaded document.")
                if not local and anonymous.get(source_path).status_code != 401:
                    raise RuntimeError("Anonymous original document access was not denied.")
                if label == "fresh-invoice" and not detail["decision"]["summary"].get(
                    "commitment_id"
                ):
                    raise RuntimeError("Validated invoice did not persist a financial reservation.")
                receipt["runs"].append(
                    {
                        "run_id": submission["run_id"],
                        "document_id": submission["document_id"],
                        "expected_outcome": expected,
                        "sha256": hashlib.sha256(pdf).hexdigest(),
                        "event_ids": [e["id"] for e in detail["events"]],
                    }
                )
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
                print(label + ": " + expected + " with stored PDF and events.", flush=True)
            print(
                "Receipt saved locally; it contains synthetic record IDs, no access token.",
                flush=True,
            )
        if args.verify_receipt:
            receipt = json.loads(args.receipt.read_text())
            if receipt["origin"] != args.origin.rstrip("/"):
                raise RuntimeError("Receipt belongs to another deployment.")
            me = request("GET", "/api/v1/me").json()
            if me["workspace_id"] != receipt["workspace_id"]:
                raise RuntimeError("Receipt belongs to another workspace.")
            for record in receipt["runs"]:
                detail = request("GET", "/api/v1/runs/" + record["run_id"]).json()
                if (
                    detail["outcome"] != record["expected_outcome"]
                    or [e["id"] for e in detail["events"]] != record["event_ids"]
                ):
                    raise RuntimeError("Decision or event history changed after restart.")
                pdf = request(
                    "GET", "/api/v1/documents/" + record["document_id"] + "/content"
                ).content
                if hashlib.sha256(pdf).hexdigest() != record["sha256"]:
                    raise RuntimeError("Original PDF did not persist.")
            print(
                "Saved decisions, exact event IDs and source PDF hashes remain intact.", flush=True
            )
        if not args.workflow and not args.verify_receipt:
            print(
                "Authenticated upload/restart checks NOT run; use --workflow with an invited reviewer token."
            )


if __name__ == "__main__":
    main()
