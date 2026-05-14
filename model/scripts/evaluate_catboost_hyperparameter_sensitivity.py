from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import KFold, train_test_split

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH, HF_DATASET_NAME, dataset_fingerprint, load_dataset_frame
from model.ml.model.training import _build_catboost_model, _predict_log_target_model, _prepare_catboost_frame
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "reports" / "hyperparameter_sensitivity_results.csv"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "reports" / "hyperparameter_sensitivity_results.json"


def compute_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_array = np.asarray(y_true, dtype=float)
    y_pred_array = np.asarray(y_pred, dtype=float)
    errors = y_true_array - y_pred_array
    non_zero_mask = y_true_array != 0
    denominator = np.sum(np.square(y_true_array - np.mean(y_true_array)))

    return {
        "MAE": float(np.mean(np.abs(errors))),
        "RMSE": float(np.sqrt(np.mean(np.square(errors)))),
        "MAPE": float(np.mean(np.abs(errors[non_zero_mask] / y_true_array[non_zero_mask])) * 100),
        "R²": float(1 - np.sum(np.square(errors)) / denominator) if denominator else float("nan"),
    }


def evaluate_cv(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    catboost_params: dict[str, Any],
    n_splits: int,
    random_state: int,
) -> dict[str, float]:
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    fold_metrics: list[dict[str, float]] = []

    for train_idx, valid_idx in splitter.split(X, y):
        model = CatBoostRegressor(**catboost_params)
        X_train = X.iloc[train_idx]
        X_valid = X.iloc[valid_idx]
        y_train = y.iloc[train_idx]
        y_valid = y.iloc[valid_idx]

        X_train_cat = _prepare_catboost_frame(X_train, feature_config)
        X_valid_cat = _prepare_catboost_frame(X_valid, feature_config)
        model.fit(
            X_train_cat,
            np.log1p(y_train),
            cat_features=feature_config.categorical_features,
            eval_set=(X_valid_cat, np.log1p(y_valid)),
            use_best_model=True,
            early_stopping_rounds=50,
            verbose=False,
        )
        predictions = _predict_log_target_model(model, X_valid_cat)
        fold_metrics.append(compute_metrics(y_valid, predictions))

    return {
        metric: float(np.mean([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    }


def evaluate_holdout(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    catboost_params: dict[str, Any],
    test_size: float,
    random_state: int,
) -> dict[str, float]:
    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
    )
    model = CatBoostRegressor(**catboost_params)
    X_train_cat = _prepare_catboost_frame(X_train, feature_config)
    X_valid_cat = _prepare_catboost_frame(X_valid, feature_config)
    model.fit(
        X_train_cat,
        np.log1p(y_train),
        cat_features=feature_config.categorical_features,
        eval_set=(X_valid_cat, np.log1p(y_valid)),
        use_best_model=True,
        early_stopping_rounds=50,
        verbose=False,
    )
    predictions = _predict_log_target_model(model, X_valid_cat)
    return compute_metrics(y_valid, predictions)


def evaluate_model(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    catboost_params: dict[str, Any],
    strategy: str,
    n_splits: int,
    test_size: float,
    random_state: int,
) -> dict[str, float]:
    if strategy == "holdout":
        return evaluate_holdout(
            X=X,
            y=y,
            feature_config=feature_config,
            catboost_params=catboost_params,
            test_size=test_size,
            random_state=random_state,
        )
    return evaluate_cv(
        X=X,
        y=y,
        feature_config=feature_config,
        catboost_params=catboost_params,
        n_splits=n_splits,
        random_state=random_state,
    )


def unique_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def sensitivity_grid(baseline_params: dict[str, Any]) -> dict[str, list[Any]]:
    baseline_learning_rate = float(baseline_params["learning_rate"])
    baseline_depth = int(baseline_params["depth"])
    baseline_iterations = int(baseline_params["iterations"])
    baseline_l2 = float(baseline_params["l2_leaf_reg"])

    return {
        "learning_rate": unique_values([
            baseline_learning_rate / 2,
            baseline_learning_rate,
            baseline_learning_rate * 2,
        ]),
        "depth": unique_values([
            max(1, baseline_depth - 2),
            baseline_depth,
            baseline_depth + 2,
        ]),
        "iterations": unique_values([
            400,
            baseline_iterations,
            1200,
        ]),
        "l2_leaf_reg": unique_values([
            1.0,
            baseline_l2,
            10.0,
        ]),
    }


def row_with_deltas(
    parameter: str,
    value: Any,
    metrics: dict[str, float],
    baseline: dict[str, float],
) -> dict[str, Any]:
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


def params_cache_key(params: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, repr(value)) for key, value in params.items()))


def run_hyperparameter_sensitivity(
    data_path: Path,
    n_splits: int,
    strategy: str,
    test_size: float,
    random_state: int,
    force_download: bool,
) -> dict[str, Any]:
    raw_df = load_dataset_frame(data_path, force_download=force_download)
    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)
    baseline_params = _build_catboost_model().get_params()
    baseline_metrics = evaluate_model(
        X=X,
        y=y,
        feature_config=feature_config,
        catboost_params=baseline_params,
        strategy=strategy,
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
    )

    rows: list[dict[str, Any]] = []
    cache: dict[tuple[tuple[str, str], ...], dict[str, float]] = {
        params_cache_key(baseline_params): baseline_metrics
    }

    for parameter, values in sensitivity_grid(baseline_params).items():
        for value in values:
            params = dict(baseline_params)
            params[parameter] = value
            key = params_cache_key(params)
            if key not in cache:
                cache[key] = evaluate_model(
                    X=X,
                    y=y,
                    feature_config=feature_config,
                    catboost_params=params,
                    strategy=strategy,
                    n_splits=n_splits,
                    test_size=test_size,
                    random_state=random_state,
                )
                print(f"Evaluated {parameter}={value}")
            rows.append(row_with_deltas(parameter, value, cache[key], baseline_metrics))

    return {
        "metadata": {
            "model_name": "catboost_regressor",
            "dataset_name": HF_DATASET_NAME,
            "dataset_path": str(data_path),
            "dataset_sha256": dataset_fingerprint(data_path) if data_path.exists() else None,
            "target_column": feature_config.target_column,
            "target_transform": "log1p",
            "inverse_transform": "expm1",
            "split_strategy": "random_kfold" if strategy == "cv" else "fixed_train_test_split",
            "n_splits": n_splits,
            "test_size": test_size if strategy == "holdout" else None,
            "shuffle": True,
            "random_state": random_state,
            "rows_before_cleaning": qc_summary["rows_before_cleaning"],
            "rows_after_cleaning": qc_summary["rows_after_cleaning"],
            "baseline_catboost_params": baseline_params,
        },
        "rows": rows,
    }


def save_outputs(payload: dict[str, Any], csv_path: Path, metadata_path: Path) -> None:
    ensure_directory(csv_path.parent)
    pd.DataFrame(payload["rows"]).to_csv(csv_path, index=False)
    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CatBoost hyperparameter sensitivity для legacy модели.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--strategy", choices=["cv", "holdout"], default="cv")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_hyperparameter_sensitivity(
        data_path=args.data_path,
        n_splits=args.n_splits,
        strategy=args.strategy,
        test_size=args.test_size,
        random_state=args.random_state,
        force_download=args.force_download,
    )
    save_outputs(payload, args.output_path, args.metadata_path)
    print(f"Saved CSV: {args.output_path}")
    print(f"Saved metadata: {args.metadata_path}")


if __name__ == "__main__":
    main()
