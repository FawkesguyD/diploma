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


DEFAULT_CSV_PATH = DEFAULT_REPORTS_DIR / "russia2021_hyperparameter_sensitivity_results.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_hyperparameter_sensitivity_results.json"


def unique_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def sensitivity_grid(params: dict[str, Any]) -> dict[str, list[Any]]:
    learning_rate = float(params["learning_rate"])
    depth = int(params["depth"])
    iterations = int(params["iterations"])
    l2_leaf_reg = float(params["l2_leaf_reg"])
    return {
        "learning_rate": unique_values([learning_rate / 2.0, learning_rate, learning_rate * 2.0]),
        "depth": unique_values([max(1, depth - 2), depth, depth + 2]),
        "iterations": unique_values([400, iterations, 1200]),
        "l2_leaf_reg": unique_values([1.0, l2_leaf_reg, 10.0]),
    }


def params_key(params: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, repr(value)) for key, value in params.items()))


def evaluate_params(
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


def row_with_deltas(parameter: str, value: Any, metrics: dict[str, float], baseline: dict[str, float]) -> dict[str, Any]:
    return {
        "Параметр": parameter,
        "Значение": value,
        "MAE": metrics["MAE"],
        "RMSE": metrics["RMSE"],
        "MAPE": metrics["MAPE"],
        "R²": metrics["R²"],
        "ΔMAPE, п.п.": metrics["MAPE"] - baseline["MAPE"],
        "ΔR²": metrics["R²"] - baseline["R²"],
    }


def run_hyperparameter_sensitivity(
    model_path: Path,
    train_pool_path: Path,
    valid_pool_path: Path,
    train_sample_size: int | None,
    valid_sample_size: int | None,
    random_state: int,
) -> dict[str, Any]:
    bundle = load_russia2021_bundle(model_path)
    features = feature_columns(bundle)
    columns = [TARGET_LOG_COLUMN, *features]
    train = read_pool_frame(train_pool_path, sample_size=train_sample_size, random_state=random_state, columns=columns)
    valid = read_pool_frame(valid_pool_path, sample_size=valid_sample_size, random_state=random_state, columns=columns)
    baseline_params = catboost_params_from_model(bundle.model)
    early_stopping_rounds = int(bundle.model.get_all_params().get("od_wait") or 50)
    categorical = list(bundle.feature_config.categorical_features)

    baseline_metrics = evaluate_params(train, valid, features, categorical, baseline_params, early_stopping_rounds)
    cache: dict[tuple[tuple[str, str], ...], dict[str, float]] = {
        params_key(baseline_params): baseline_metrics
    }

    rows: list[dict[str, Any]] = []
    for parameter, values in sensitivity_grid(baseline_params).items():
        for value in values:
            params = dict(baseline_params)
            params[parameter] = value
            key = params_key(params)
            if key not in cache:
                cache[key] = evaluate_params(train, valid, features, categorical, params, early_stopping_rounds)
                print(f"Evaluated {parameter}={value}")
            rows.append(row_with_deltas(parameter, value, cache[key], baseline_metrics))

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
            "baseline_catboost_params": baseline_params,
            "early_stopping_rounds": early_stopping_rounds,
            "note": "This is sensitivity analysis, not hyperparameter tuning. The production artifact is not modified.",
        },
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CatBoost hyperparameter sensitivity for Russia 2021 model.")
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
    payload = run_hyperparameter_sensitivity(
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
