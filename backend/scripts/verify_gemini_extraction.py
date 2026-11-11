"""Explicit local provider smoke check; no database, invoice values or secrets are printed."""

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.extraction.pdf import PDFError, pdf_process
from app.extraction.pipeline import ExtractionModeFailure, structure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--mode", choices=["GEMINI", "AUTO"], default="GEMINI")
    args = parser.parse_args()
    settings = get_settings()
    if not args.pdf.is_file() or args.pdf.stat().st_size > settings.max_upload_bytes:
        parser.error("Choose an existing invoice PDF within the configured upload size limit.")
    try:
        pages = pdf_process(args.pdf, True)["pages"]
        result = structure(pages, "local-verification-only", args.mode)
    except ExtractionModeFailure as exc:
        print(
            json.dumps(
                {
                    "provider": "NONE",
                    "requested_model": settings.gemini_model,
                    "provider_diagnostics": exc.metadata["provider_diagnostics"],
                    "financial_decision": "not_run",
                }
            )
        )
        return 2
    except PDFError:
        print(json.dumps({"category": "pdf_reading_failed", "financial_decision": "not_run"}))
        return 2
    evidence = [value for value in result["fields"].values() if isinstance(value, dict)]
    evidence += [value for item in result["fields"].get("items", []) for value in item.values()]
    print(
        json.dumps(
            {
                "requested_model": settings.gemini_model,
                "provider": result["provider"],
                "actual_model": result["model"],
                "provider_diagnostics": result["provider_diagnostics"],
                "verified_values": sum(bool(value.get("verified")) for value in evidence),
                "issues_count": len(result["fields"].get("issues", [])),
                "financial_decision": "not_run",
            }
        )
    )
    return 0 if result["provider"] == "GEMINI" else 2


if __name__ == "__main__":
    raise SystemExit(main())
