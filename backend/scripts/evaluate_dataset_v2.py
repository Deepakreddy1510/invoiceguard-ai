import argparse
import json
import os
from pathlib import Path

from scripts.dataset_v2.runner import evaluate

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["extraction", "gold", "worker"], required=True)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--provider", choices=["fallback", "gemini"], default="fallback")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    admin = os.environ.get(
        "EVAL_ADMIN_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
    )
    print(json.dumps(evaluate(args.mode, args.split, args.provider, admin, args.report), indent=2))
