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
    DEFAULT_TRAIN_POOL_PATH,
    DEFAULT_VALID_POOL_PATH,
    TARGET_LOG_COLUMN,
    catboost_params_from_model,
    compute_metrics,
    feature_columns,
    load_russia2021_bundle,
    prepare_catboost_frame,
    read_pool_frame,
    save_json,
    train_catboost,
)


DEFAULT_CSV_PATH = DEFAULT_REPORTS_DIR / "russia2021_feature_ablation_results.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_feature_ablation_results.json"

FEATURE_GROUPS: dict[str, list[str]] = {
    "Площадь": ["total_area_m2", "living_area_m2", "kitchen_area_m2", "area", "kitchen_area", "area_per_room"],
    "Этажность": ["floor", "total_floors", "level", "levels", "floor_ratio", "is_first_floor", "is_top_floor"],
    "География": ["latitude", "longitude", "district", "has_coordinates"],
    "Состояние и дом": ["building_type", "building_series", "condition", "year_built", "building_age"],
    "Остальные категориальные признаки": [
        "heating",
        "gas_supply",
        "bathroom",
        "balcony",
        "parking",
        "furniture",
        "flooring",
        "door_type",
        "has_landline_phone",
        "internet",
        "mortgage",
        "seller_type",
    ],
}


def row_with_deltas(label: str, metrics: dict[str, float], baseline: dict[str, float], removed: list[str], missing: list[str]) -> dict[str, Any]:
    return {
        "Удаленный признак/группа": label,
        "removed_features": ", ".join(removed),
        "missing_requested_features": ", ".join(missing),
        "MAE": metrics["MAE"],
        "RMSE": metrics["RMSE"],
        "MAPE": metrics["MAPE"],
        "R²": metrics["R²"],
        "ΔMAE": metrics["MAE"] - baseline["MAE"],
        "ΔRMSE": metrics["RMSE"] - baseline["RMSE"],
        "ΔMAPE, п.п.": metrics["MAPE"] - baseline["MAPE"],
        "ΔR²": metrics["R²"] - baseline["R²"],
    }


def evaluate_config(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    features: list[str],
    categorical_features: list[str],
    params: dict[str, Any],
    early_stopping_rounds: int,
) -> dict[str, float]:
    x_train = train.loc[:, features]
    x_valid = valid.loc[:, features]
    y_train_log = train[TARGET_LOG_COLUMN].to_numpy(dtype=float)
    y_valid_log = valid[TARGET_LOG_COLUMN].to_numpy(dtype=float)
    y_valid = np.exp(y_valid_log)
    model = train_catboost(
        x_train=x_train,
        y_train_log=y_train_log,
        x_valid=x_valid,
        y_valid_log=y_valid_log,
        categorical_features=categorical_features,
        params=params,
        early_stopping_rounds=early_stopping_rounds,
    )
    raw_predictions = model.predict(prepare_catboost_frame(x_valid, categorical_features))
    return compute_metrics(y_valid, np.exp(np.asarray(raw_predictions, dtype=float)))


def run_feature_ablation(
    model_path: Path,
    train_pool_path: Path,
    valid_pool_path: Path,
    train_sample_size: int | None,
    valid_sample_size: int | None,
    random_state: int,
) -> dict[str, Any]:
    bundle = load_russia2021_bundle(model_path)
    all_features = feature_columns(bundle)
    columns = [TARGET_LOG_COLUMN, *all_features]
    train = read_pool_frame(train_pool_path, sample_size=train_sample_size, random_state=random_state, columns=columns)
    valid = read_pool_frame(valid_pool_path, sample_size=valid_sample_size, random_state=random_state, columns=columns)
    params = catboost_params_from_model(bundle.model)
    early_stopping_rounds = int(bundle.model.get_all_params().get("od_wait") or 50)
    categorical = list(bundle.feature_config.categorical_features)

    baseline_metrics = evaluate_config(train, valid, all_features, categorical, params, early_stopping_rounds)
    rows = [row_with_deltas("baseline", baseline_metrics, baseline_metrics, [], [])]

    for label, requested_features in FEATURE_GROUPS.items():
        removed = [feature for feature in requested_features if feature in all_features]
        missing = [feature for feature in requested_features if feature not in all_features]
        if not removed:
            rows.append(
                row_with_deltas(
                    f"Группа: {label}",
                    baseline_metrics,
                    baseline_metrics,
                    [],
                    missing,
                )
            )
            continue
        reduced_features = [feature for feature in all_features if feature not in removed]
        reduced_categorical = [feature for feature in categorical if feature in reduced_features]
        metrics = evaluate_config(train, valid, reduced_features, reduced_categorical, params, early_stopping_rounds)
        rows.append(row_with_deltas(f"Группа: {label}", metrics, baseline_metrics, removed, missing))
        print(f"Evaluated group: {label}")

    return {
        "metadata": {
            "model_path": str(model_path),
            "model_name": bundle.model_name,
            "target_column": bundle.target_column,
            "target_transform": bundle.target_transform,
            "inverse_transform": "exp",
            "base_currency": bundle.base_currency,
            "mape_unit": "percent",
            "train_pool_path": str(train_pool_path),
            "valid_pool_path": str(valid_pool_path),
            "train_rows_used": int(len(train)),
            "valid_rows_used": int(len(valid)),
            "train_sample_size": train_sample_size,
            "valid_sample_size": valid_sample_size,
            "random_state": random_state,
            "catboost_params": params,
            "early_stopping_rounds": early_stopping_rounds,
            "note": "Feature ablation retrains CatBoost on the prepared Russia 2021 train pool. If sample sizes are set, results are sensitivity estimates on deterministic samples, not full retraining.",
        },
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feature ablation for Russia 2021 CatBoost model.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--train-pool-path", type=Path, default=DEFAULT_TRAIN_POOL_PATH)
    parser.add_argument("--valid-pool-path", type=Path, default=DEFAULT_VALID_POOL_PATH)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--train-sample-size", type=int, default=250_000)
    parser.add_argument("--valid-sample-size", type=int, default=100_000)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_feature_ablation(
        model_path=args.model_path,
        train_pool_path=args.train_pool_path,
        valid_pool_path=args.valid_pool_path,
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
