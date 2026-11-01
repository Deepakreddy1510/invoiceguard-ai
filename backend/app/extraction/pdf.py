"""Resource-bounded subprocess entrypoint for untrusted PDF/OCR work."""

import csv
import json
import os
import resource
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

import pymupdf

MAX_PAGES = 20
MAX_PIXELS = 18_000_000


class PDFError(ValueError):
    pass


def read_pdf(path: str, extract: bool = True) -> dict:
    with pymupdf.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass or not 1 <= len(doc) <= MAX_PAGES:
            raise PDFError("PDF must be readable, unencrypted and contain 1–20 pages.")
        pages = []
        for number, page in enumerate(doc, 1):
            if (
                page.rect.width <= 0
                or page.rect.height <= 0
                or page.rect.width * page.rect.height * 4 > MAX_PIXELS
            ):
                raise PDFError("Page exceeds rendering limits.")
            text = "\n".join(
                block[4].strip() for block in page.get_text("blocks", sort=True) if block[6] == 0
            )
            if not extract:
                continue
            word_data = [
                {"text": w[4], "x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3]}
                for w in page.get_text("words")
            ]
            method = "PDF_TEXT"
            # Image-bearing pages with little useful text need OCR; blank pages also follow OCR.
            if len(text.strip()) < 40 or (page.get_images() and len(text.strip()) < 200):
                with tempfile.TemporaryDirectory() as temp:
                    image = Path(temp) / "page.png"
                    page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(image)
                    result = subprocess.run(
                        ["tesseract", str(image), "stdout", "-l", "eng", "--psm", "3", "tsv"],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=True,
                    )
                    groups = {}
                    word_data = []
                    for word in csv.DictReader(StringIO(result.stdout), delimiter="\t"):
                        if word.get("level") != "5" or not word.get("text", "").strip():
                            continue
                        key = (word["block_num"], word["par_num"], word["line_num"])
                        groups.setdefault(key, []).append(word)
                        word_data.append(
                            {
                                "text": word["text"],
                                "x0": int(word["left"]) / 2,
                                "y0": int(word["top"]) / 2,
                                "x1": (int(word["left"]) + int(word["width"])) / 2,
                                "y1": (int(word["top"]) + int(word["height"])) / 2,
                            }
                        )
                    lines = []
                    for words in groups.values():
                        words.sort(key=lambda w: int(w["left"]))
                        line = ""
                        previous_right = None
                        for word in words:
                            left = int(word["left"])
                            if previous_right is not None and left - previous_right > 80:
                                lines.append(line)
                                line = ""
                            line += (" " if line else "") + word["text"]
                            previous_right = left + int(word["width"])
                        if line:
                            lines.append(line)
                    text = "\n".join(lines)
                method = "OCR"
            pages.append(
                {
                    "page": number,
                    "text": text[:100_000],
                    "method": method,
                    "words": word_data[:20000],
                }
            )
        return {"page_count": len(doc), "pages": pages}


def pdf_process(path: Path, extract: bool) -> dict:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.extraction.pdf",
                "extract" if extract else "inspect",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=55,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            check=True,
        )
        payload = json.loads(result.stdout)
        if "error" in payload:
            raise PDFError(payload["error"])
        return payload
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise PDFError("PDF/OCR processing failed or exceeded resource limits.") from exc


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    try:
        print(json.dumps(read_pdf(sys.argv[2], sys.argv[1] == "extract")))
    except Exception:
        print(
            json.dumps(
                {
                    "error": "PDF unreadable or OCR failed; check document quality and Tesseract installation."
                }
            )
        )
