from __future__ import annotations

import argparse
import json
import sys

from model.apps.normalization.service import normalize_raw_listing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Нормализация одного сырого объекта недвижимости из JSON.")
    parser.add_argument("--json", required=True, help="JSON-объект исходного объявления.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_payload = json.loads(args.json)
    result = normalize_raw_listing(raw_payload)
    json.dump(
        {
            "normalized_payload": result.normalized_payload,
            "status": result.status,
            "errors": result.errors,
            "warnings": result.warnings,
            "is_train_eligible": result.is_train_eligible,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
