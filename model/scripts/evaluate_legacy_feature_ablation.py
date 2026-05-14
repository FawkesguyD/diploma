from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE
from model.scripts.evaluate_feature_ablation import run_feature_ablation, save_outputs


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "reports" / "legacy_feature_ablation_results.csv"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "reports" / "legacy_feature_ablation_results.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feature ablation for legacy CatBoost model.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--strategy", choices=["cv", "holdout"], default="holdout")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--groups-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_feature_ablation(
        data_path=args.data_path,
        n_splits=args.n_splits,
        strategy=args.strategy,
        test_size=args.test_size,
        random_state=args.random_state,
        force_download=args.force_download,
        groups_only=args.groups_only,
    )
    payload["metadata"]["report_prefix"] = "legacy"
    save_outputs(payload, args.output_path, args.metadata_path)
    print(f"Saved legacy feature ablation CSV: {args.output_path}")
    print(f"Saved legacy feature ablation metadata: {args.metadata_path}")


if __name__ == "__main__":
    main()
