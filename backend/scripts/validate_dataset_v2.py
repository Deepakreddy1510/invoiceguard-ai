import argparse
import json

from scripts.dataset_v2.integrity import validate_answers, validate_public

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-heldout", action="store_true")
    args = parser.parse_args()
    results = [validate_public(), validate_answers("development")]
    if args.include_heldout:
        results.append(validate_answers("heldout"))
    print(json.dumps(results, indent=2))
