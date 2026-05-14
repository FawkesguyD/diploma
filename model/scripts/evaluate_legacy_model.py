from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH, HF_DATASET_NAME, dataset_fingerprint, load_dataset_frame
from model.ml.model.evaluate import compute_regression_metrics
from model.ml.model.normalization import fill_categorical_features_for_catboost
from model.ml.model.persistence import inverse_transform_predictions, load_model_bundle
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory


DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "best_model.joblib"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "ml" / "reports" / "catboost_regressor_validation_report.json"
DEFAULT_CSV_PATH = PROJECT_ROOT / "reports" / "legacy_validation_metrics.csv"
DEFAULT_JSON_PATH = PROJECT_ROOT / "reports" / "legacy_validation_metrics.json"
USD_TO_RUB = 90.0


def compute_percent_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    metrics = compute_regression_metrics(y_true, y_pred)
    metrics["mape_percent"] = metrics["mape"] * 100.0
    return metrics


def load_existing_report(report_path: Path) -> dict[str, Any] | None:
    if not report_path.exists():
        return None
    with report_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def evaluate_artifact(
    model_path: Path,
    data_path: Path,
    test_size: float,
    random_state: int,
    force_download: bool,
) -> dict[str, Any]:
    bundle = load_model_bundle(model_path)
    raw_df = load_dataset_frame(data_path, force_download=force_download)
    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)
    _, X_valid, _, y_valid = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
    )

    X_valid = X_valid[bundle.feature_config.feature_columns]
    X_valid_cat = fill_categorical_features_for_catboost(
        X_valid,
        bundle.feature_config.categorical_features,
    )
    raw_predictions = bundle.model.predict(X_valid_cat)
    predictions = inverse_transform_predictions(raw_predictions, bundle.target_transform)
    predictions = np.clip(np.asarray(predictions, dtype=float), a_min=0.0, a_max=None)
    metrics = compute_percent_metrics(y_valid, predictions)

    return {
        "metadata": {
            "source": "recomputed_from_artifact",
            "model_path": str(model_path),
            "model_name": bundle.model_name,
            "model_type": f"{bundle.model.__class__.__module__}.{bundle.model.__class__.__name__}",
            "dataset_name": HF_DATASET_NAME,
            "dataset_path": str(data_path),
            "dataset_sha256": dataset_fingerprint(data_path) if data_path.exists() else None,
            "target_column": bundle.target_column,
            "target_currency": bundle.base_currency,
            "target_transform": bundle.target_transform,
            "inverse_transform": "expm1" if bundle.target_transform == "log1p" else "identity",
            "split_strategy": "fixed_train_test_split",
            "test_size": test_size,
            "random_state": random_state,
            "rows_before_cleaning": qc_summary["rows_before_cleaning"],
            "rows_after_cleaning": qc_summary["rows_after_cleaning"],
            "validation_rows": int(len(y_valid)),
            "usd_to_rub_rate_for_article": USD_TO_RUB,
        },
        "metrics": {
            "MAE": metrics["mae"],
            "RMSE": metrics["rmse"],
            "MAPE": metrics["mape_percent"],
            "R²": metrics["r2"],
            "MAE_RUB_at_90": metrics["mae"] * USD_TO_RUB,
            "RMSE_RUB_at_90": metrics["rmse"] * USD_TO_RUB,
        },
    }


def payload_from_existing_report(report: dict[str, Any], model_path: Path) -> dict[str, Any]:
    metrics = report["validation_metrics"]
    return {
        "metadata": {
            "source": "ml/reports/catboost_regressor_validation_report.json",
            "model_path": str(model_path),
            "model_name": report.get("model_name", "catboost_regressor"),
            "target_column": "price_usd",
            "target_currency": "USD",
            "target_transform": "log1p",
            "inverse_transform": "expm1",
            "usd_to_rub_rate_for_article": USD_TO_RUB,
            "cross_validation": report.get("cross_validation", {}),
            "notes": report.get("notes", {}),
        },
        "metrics": {
            "MAE": float(metrics["mae"]),
            "RMSE": float(metrics["rmse"]),
            "MAPE": float(metrics["mape"]) * 100.0,
            "R²": float(metrics["r2"]),
            "MAE_RUB_at_90": float(metrics["mae"]) * USD_TO_RUB,
            "RMSE_RUB_at_90": float(metrics["rmse"]) * USD_TO_RUB,
        },
    }


def save_outputs(payload: dict[str, Any], csv_path: Path, json_path: Path) -> None:
    ensure_directory(csv_path.parent)
    pd.DataFrame([payload["metrics"]]).to_csv(csv_path, index=False)
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate legacy CatBoost model.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--existing-report-path", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    existing_report = load_existing_report(args.existing_report_path)
    if existing_report is not None and not args.recompute:
        payload = payload_from_existing_report(existing_report, args.model_path)
    else:
        payload = evaluate_artifact(
            model_path=args.model_path,
            data_path=args.data_path,
            test_size=args.test_size,
            random_state=args.random_state,
            force_download=args.force_download,
        )
    save_outputs(payload, args.csv_path, args.json_path)
    print(f"Saved validation CSV: {args.csv_path}")
    print(f"Saved validation JSON: {args.json_path}")


if __name__ == "__main__":
    main()
