from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.apps.analytics_service.config import FORMULA_BASELINE_COEFFICIENTS
from model.scripts.russia2021_analysis_common import (
    DEFAULT_MODEL_PATH,
    DEFAULT_REPORTS_DIR,
    DEFAULT_TRAIN_POOL_PATH,
    DEFAULT_VALID_POOL_PATH,
    TARGET_LOG_COLUMN,
    compute_metrics,
    feature_columns,
    load_russia2021_bundle,
    predict_bundle_on_frame,
    read_pool_frame,
    save_json,
)


DEFAULT_CSV_PATH = DEFAULT_REPORTS_DIR / "russia2021_method_comparison.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_method_comparison.json"
DEFAULT_LINEAR_PATH = PROJECT_ROOT / "ml" / "artifacts" / "linear_regression_baseline.joblib"
STAT_GROUPS = (
    ("region", "object_type", "building_type", "rooms"),
    ("region", "object_type", "rooms"),
    ("region", "rooms"),
    ("region",),
)


def price_from_log(frame: pd.DataFrame) -> np.ndarray:
    return np.exp(frame[TARGET_LOG_COLUMN].to_numpy(dtype=float))


def train_stat_medians(train: pd.DataFrame) -> dict[tuple[str, ...], pd.Series]:
    frame = train.copy()
    frame["price"] = price_from_log(frame)
    frame["price_per_m2"] = frame["price"] / frame["area"].replace({0: np.nan})
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["price_per_m2"])
    medians: dict[tuple[str, ...], pd.Series] = {}
    for group in STAT_GROUPS:
        medians[group] = frame.groupby(list(group), dropna=False)["price_per_m2"].median()
    medians[tuple()] = pd.Series({"__global__": float(frame["price_per_m2"].median())})
    return medians


def lookup_median(row: pd.Series, medians: dict[tuple[str, ...], pd.Series]) -> float:
    for group in STAT_GROUPS:
        key: Any = row[group[0]] if len(group) == 1 else tuple(row[column] for column in group)
        values = medians[group]
        if key in values.index:
            result = float(values.loc[key])
            if np.isfinite(result):
                return result
    return float(medians[tuple()].loc["__global__"])


def predict_statistical(train: pd.DataFrame, valid: pd.DataFrame) -> np.ndarray:
    medians = train_stat_medians(train)
    price_per_m2 = valid.apply(lambda row: lookup_median(row, medians), axis=1).to_numpy(dtype=float)
    return price_per_m2 * valid["area"].to_numpy(dtype=float)


def predict_heuristic(valid: pd.DataFrame) -> np.ndarray:
    c = FORMULA_BASELINE_COEFFICIENTS
    predictions = (
        c["intercept"]
        + valid["area"].astype(float) * c["area"]
        + valid["kitchen_area"].astype(float) * c["kitchen_area"]
        + valid["rooms"].astype(float) * c["rooms"]
        + valid["level"].astype(float) * c["level"]
        + valid["levels"].astype(float) * c["levels"]
    )
    return predictions.clip(lower=0).to_numpy(dtype=float)


def linear_artifact_compatible(path: Path, expected_features: list[str]) -> tuple[bool, dict[str, Any]]:
    if not path.exists():
        return False, {"artifact_path": str(path), "reason": "artifact missing"}
    payload = joblib.load(path)
    if not isinstance(payload, dict):
        return False, {"artifact_path": str(path), "reason": "unexpected artifact type"}
    config = payload.get("feature_config", {})
    features = list(config.get("numerical_features", [])) + list(config.get("categorical_features", []))
    target_column = payload.get("target_column") or config.get("target_column")
    base_currency = (payload.get("base_currency") or "").upper()
    compatible = features == expected_features and target_column == "price" and base_currency in {"", "RUB"}
    return compatible, {
        "artifact_path": str(path),
        "target_column": target_column,
        "base_currency": base_currency or None,
        "feature_count": len(features),
        "expected_feature_count": len(expected_features),
        "reason": None if compatible else "artifact schema is not compatible with Russia 2021 RUB features",
    }


def metrics_row(method: str, y_true: np.ndarray, y_pred: np.ndarray, source: str) -> dict[str, Any]:
    metrics = compute_metrics(y_true, y_pred)
    return {
        "Метод": method,
        "MAE": metrics["MAE"],
        "RMSE": metrics["RMSE"],
        "MAPE": metrics["MAPE"],
        "R²": metrics["R²"],
        "currency": "RUB",
        "source": source,
    }


def run_comparison(
    model_path: Path,
    train_pool_path: Path,
    valid_pool_path: Path,
    linear_model_path: Path,
    train_sample_size: int | None,
    valid_sample_size: int | None,
    random_state: int,
) -> dict[str, Any]:
    bundle = load_russia2021_bundle(model_path)
    features = feature_columns(bundle)
    columns = sorted(set([TARGET_LOG_COLUMN, *features]))
    train = read_pool_frame(train_pool_path, sample_size=train_sample_size, random_state=random_state, columns=columns)
    valid = read_pool_frame(valid_pool_path, sample_size=valid_sample_size, random_state=random_state, columns=columns)
    y_true = price_from_log(valid)

    rows = [
        metrics_row(
            "Статистический метод",
            y_true,
            predict_statistical(train, valid),
            "median price_per_m2 by train_pool groups with fallback to global train median",
        ),
        metrics_row(
            "Эвристический скоринг",
            y_true,
            predict_heuristic(valid),
            "apps.analytics_service.config.FORMULA_BASELINE_COEFFICIENTS",
        ),
        metrics_row(
            "best_model_russia2021",
            y_true,
            predict_bundle_on_frame(bundle, valid),
            str(model_path),
        ),
    ]
    linear_compatible, linear_metadata = linear_artifact_compatible(linear_model_path, features)
    return {
        "metadata": {
            "model_path": str(model_path),
            "train_pool_path": str(train_pool_path),
            "valid_pool_path": str(valid_pool_path),
            "train_rows_used": int(len(train)),
            "valid_rows_used": int(len(valid)),
            "train_sample_size": train_sample_size,
            "valid_sample_size": valid_sample_size,
            "random_state": random_state,
            "target_column": bundle.target_column,
            "target_transform": bundle.target_transform,
            "base_currency": bundle.base_currency,
            "mape_unit": "percent",
            "linear_regression_artifact": linear_metadata,
            "linear_regression_included": linear_compatible,
            "note": "Ranking metrics are not computed here because transaction relevance labels are absent.",
        },
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Method comparison for Russia 2021 model.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--train-pool-path", type=Path, default=DEFAULT_TRAIN_POOL_PATH)
    parser.add_argument("--valid-pool-path", type=Path, default=DEFAULT_VALID_POOL_PATH)
    parser.add_argument("--linear-model-path", type=Path, default=DEFAULT_LINEAR_PATH)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--train-sample-size", type=int, default=None)
    parser.add_argument("--valid-sample-size", type=int, default=100_000)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_comparison(
        model_path=args.model_path,
        train_pool_path=args.train_pool_path,
        valid_pool_path=args.valid_pool_path,
        linear_model_path=args.linear_model_path,
        train_sample_size=args.train_sample_size,
        valid_sample_size=args.valid_sample_size,
        random_state=args.random_state,
    )
    args.csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(payload["rows"]).to_csv(args.csv_path, index=False)
    save_json(payload, args.json_path)
    print(f"Saved CSV: {args.csv_path}")
    print(f"Saved JSON: {args.json_path}")


if __name__ == "__main__":
    main()
