import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "datasets/synthetic-v2"
PRIVATE = ROOT / "evaluation/synthetic-v2"
VERSION = "synthetic-v2.0.0"
SEED = 20261101
WORKSPACE = "00000000-0000-0000-0000-000000000001"
UNITS = {"USD": 2, "INR": 2, "EUR": 2, "GBP": 2, "JPY": 0, "KWD": 3}


def uid(label):
    return str(uuid5(NAMESPACE_URL, VERSION + "/" + label))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load(path):
    return json.loads(Path(path).read_text())


def source_hashes():
    return {
        str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "backend/app").rglob("*.py"))
    }
