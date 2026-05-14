from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.scripts.russia2021_analysis_common import (
    DEFAULT_MODEL_PATH,
    DEFAULT_REPORTS_DIR,
    DEFAULT_VALID_POOL_PATH,
    TARGET_LOG_COLUMN,
    compute_metrics,
    feature_columns,
    load_russia2021_bundle,
    predict_bundle_on_frame,
    read_pool_frame,
    save_json,
)


DEFAULT_CSV_PATH = DEFAULT_REPORTS_DIR / "russia2021_validation_metrics.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_validation_metrics.json"


def evaluate_model(
    model_path: Path,
    valid_pool_path: Path,
    *,
    sample_size: int | None,
    random_state: int,
) -> dict[str, Any]:
    bundle = load_russia2021_bundle(model_path)
    columns = [TARGET_LOG_COLUMN, *feature_columns(bundle)]
    valid = read_pool_frame(
        valid_pool_path,
        sample_size=sample_size,
        random_state=random_state,
        columns=columns,
    )
    y_true = np.exp(valid[TARGET_LOG_COLUMN].to_numpy(dtype=float))
    predictions = predict_bundle_on_frame(bundle, valid)
    metrics = compute_metrics(y_true, predictions)

    row = {
        "fold_or_sample": "validation" if sample_size is None else "validation_sample",
        "rows": int(len(valid)),
        "MAE": metrics["MAE"],
        "RMSE": metrics["RMSE"],
        "MAPE": metrics["MAPE"],
        "R²": metrics["R²"],
        "currency": bundle.base_currency,
    }
    return {
        "metadata": {
            "model_path": str(model_path),
            "model_name": bundle.model_name,
            "model_type": f"{type(bundle.model).__module__}.{type(bundle.model).__qualname__}",
            "valid_pool_path": str(valid_pool_path),
            "target_column": bundle.target_column,
            "target_log_column": TARGET_LOG_COLUMN,
            "target_transform": bundle.target_transform,
            "inverse_transform": "exp",
            "base_currency": bundle.base_currency,
            "mape_unit": "percent",
            "sample_size": sample_size,
            "random_state": random_state,
        },
        "metrics": row,
        "metrics_fractional": {
            "mae": metrics["MAE"],
            "rmse": metrics["RMSE"],
            "mape": metrics["mape_fraction"],
            "r2": metrics["R²"],
        },
    }


def save_csv(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([payload["metrics"]]).to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validation metrics for best_model_russia2021.joblib.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--valid-pool-path", type=Path, default=DEFAULT_VALID_POOL_PATH)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = evaluate_model(
        model_path=args.model_path,
        valid_pool_path=args.valid_pool_path,
        sample_size=args.sample_size,
        random_state=args.random_state,
    )
    save_csv(payload, args.csv_path)
    save_json(payload, args.json_path)
    print(f"Saved CSV: {args.csv_path}")
    print(f"Saved JSON: {args.json_path}")


if __name__ == "__main__":
    main()
