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
from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.training import _build_catboost_model, _predict_log_target_model, _prepare_catboost_frame
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory


DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "reports" / "feature_ablation_results.csv"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "reports" / "feature_ablation_results.json"

FEATURE_GROUPS: dict[str, list[str]] = {
    "Площадь": [
        "total_area_m2",
        "living_area_m2",
        "kitchen_area_m2",
        "area_per_room",
    ],
    "Этажность": [
        "floor",
        "total_floors",
        "floor_ratio",
        "is_first_floor",
        "is_top_floor",
    ],
    "География": [
        "latitude",
        "longitude",
        "district",
        "has_coordinates",
    ],
    "Состояние и дом": [
        "building_type",
        "building_series",
        "condition",
        "year_built",
        "building_age",
    ],
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


def filtered_feature_config(feature_config: FeatureConfig, removed_features: set[str]) -> FeatureConfig:
    return FeatureConfig(
        target_column=feature_config.target_column,
        numerical_features=[
            feature
            for feature in feature_config.numerical_features
            if feature not in removed_features
        ],
        categorical_features=[
            feature
            for feature in feature_config.categorical_features
            if feature not in removed_features
        ],
        derived_numeric_features=[
            feature
            for feature in feature_config.derived_numeric_features
            if feature not in removed_features
        ],
        excluded_columns=feature_config.excluded_columns,
        log_target=feature_config.log_target,
    )


def build_model(catboost_params: dict[str, Any]) -> CatBoostRegressor:
    return CatBoostRegressor(**catboost_params)


def evaluate_cv(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: FeatureConfig,
    catboost_params: dict[str, Any],
    n_splits: int,
    random_state: int,
) -> dict[str, float]:
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    fold_metrics: list[dict[str, float]] = []

    for train_idx, valid_idx in splitter.split(X, y):
        model = build_model(catboost_params)
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
    feature_config: FeatureConfig,
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
    model = build_model(catboost_params)
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
    feature_config: FeatureConfig,
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


def row_with_deltas(
    label: str,
    metrics: dict[str, float],
    baseline: dict[str, float],
) -> dict[str, Any]:
    return {
        "Удаленный признак/группа": label,
        "MAE": metrics["MAE"],
        "RMSE": metrics["RMSE"],
        "MAPE": metrics["MAPE"],
        "R²": metrics["R²"],
        "ΔMAE": metrics["MAE"] - baseline["MAE"],
        "ΔRMSE": metrics["RMSE"] - baseline["RMSE"],
        "ΔMAPE, п.п.": metrics["MAPE"] - baseline["MAPE"],
        "ΔR²": metrics["R²"] - baseline["R²"],
    }


def run_feature_ablation(
    data_path: Path,
    n_splits: int,
    strategy: str,
    test_size: float,
    random_state: int,
    force_download: bool,
    groups_only: bool,
) -> dict[str, Any]:
    raw_df = load_dataset_frame(data_path, force_download=force_download)
    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)
    catboost_params = _build_catboost_model().get_params()

    baseline_metrics = evaluate_model(
        X=X,
        y=y,
        feature_config=feature_config,
        catboost_params=catboost_params,
        strategy=strategy,
        n_splits=n_splits,
        test_size=test_size,
        random_state=random_state,
    )

    rows = [row_with_deltas("baseline", baseline_metrics, baseline_metrics)]

    candidates: list[tuple[str, list[str]]] = []
    for group_name, group_features in FEATURE_GROUPS.items():
        existing = [feature for feature in group_features if feature in X.columns]
        if existing:
            candidates.append((f"Группа: {group_name}", existing))

    if not groups_only:
        for feature in feature_config.feature_columns:
            if feature in X.columns:
                candidates.append((f"Признак: {feature}", [feature]))

    for label, removed in candidates:
        removed_features = set(removed)
        X_reduced = X.drop(columns=list(removed_features), errors="ignore")
        reduced_config = filtered_feature_config(feature_config, removed_features)
        metrics = evaluate_model(
            X=X_reduced,
            y=y,
            feature_config=reduced_config,
            catboost_params=catboost_params,
            strategy=strategy,
            n_splits=n_splits,
            test_size=test_size,
            random_state=random_state,
        )
        rows.append(row_with_deltas(label, metrics, baseline_metrics))
        print(f"Evaluated {label}")

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
            "numerical_features": feature_config.numerical_features,
            "categorical_features": feature_config.categorical_features,
            "catboost_params": catboost_params,
            "groups_only": groups_only,
        },
        "rows": rows,
    }


def save_outputs(payload: dict[str, Any], csv_path: Path, metadata_path: Path) -> None:
    ensure_directory(csv_path.parent)
    pd.DataFrame(payload["rows"]).to_csv(csv_path, index=False)
    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feature ablation для legacy CatBoost модели.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--strategy", choices=["cv", "holdout"], default="cv")
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
    save_outputs(payload, args.output_path, args.metadata_path)
    print(f"Saved CSV: {args.output_path}")
    print(f"Saved metadata: {args.metadata_path}")


if __name__ == "__main__":
    main()
