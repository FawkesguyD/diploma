from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.scripts.russia2021_analysis_common import (
    DEFAULT_MODEL_PATH,
    DEFAULT_REPORTS_DIR,
    DEFAULT_TRAIN_POOL_PATH,
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


DEFAULT_CSV_PATH = DEFAULT_REPORTS_DIR / "russia2021_cv_results.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_cv_results.json"


def run_cv(
    model_path: Path,
    train_pool_path: Path,
    sample_size: int | None,
    n_splits: int,
    random_state: int,
) -> dict[str, Any]:
    bundle = load_russia2021_bundle(model_path)
    features = feature_columns(bundle)
    columns = [TARGET_LOG_COLUMN, *features]
    frame = read_pool_frame(train_pool_path, sample_size=sample_size, random_state=random_state, columns=columns)
    params = catboost_params_from_model(bundle.model)
    early_stopping_rounds = int(bundle.model.get_all_params().get("od_wait") or 50)
    categorical = list(bundle.feature_config.categorical_features)
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)

    fold_rows: list[dict[str, Any]] = []
    for fold_index, (train_idx, valid_idx) in enumerate(splitter.split(frame), start=1):
        train = frame.iloc[train_idx]
        valid = frame.iloc[valid_idx]
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
            categorical_features=categorical,
            params=params,
            early_stopping_rounds=early_stopping_rounds,
        )
        raw_predictions = model.predict(prepare_catboost_frame(x_valid, categorical))
        metrics = compute_metrics(y_valid, np.exp(np.asarray(raw_predictions, dtype=float)))
        fold_rows.append(
            {
                "fold": fold_index,
                "train_rows": int(len(train)),
                "valid_rows": int(len(valid)),
                "MAE": metrics["MAE"],
                "RMSE": metrics["RMSE"],
                "MAPE": metrics["MAPE"],
                "R²": metrics["R²"],
            }
        )
        print(f"Evaluated fold {fold_index}")

    metric_names = ["MAE", "RMSE", "MAPE", "R²"]
    mean_row = {
        "fold": "mean",
        "train_rows": None,
        "valid_rows": None,
        **{metric: float(np.mean([row[metric] for row in fold_rows])) for metric in metric_names},
    }
    std_row = {
        "fold": "std",
        "train_rows": None,
        "valid_rows": None,
        **{metric: float(np.std([row[metric] for row in fold_rows])) for metric in metric_names},
    }
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
            "rows_used": int(len(frame)),
            "sample_size": sample_size,
            "n_splits": n_splits,
            "random_state": random_state,
            "catboost_params": params,
            "early_stopping_rounds": early_stopping_rounds,
            "note": "Cross-validation retrains models. If sample_size is set, the result is a deterministic sampled CV estimate for the Russia 2021 training pool.",
        },
        "folds": fold_rows,
        "summary": {"mean": mean_row, "std": std_row},
        "rows": fold_rows + [mean_row, std_row],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="5-fold CatBoost CV for Russia 2021 prepared train pool.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--train-pool-path", type=Path, default=DEFAULT_TRAIN_POOL_PATH)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--sample-size", type=int, default=250_000)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_cv(
        model_path=args.model_path,
        train_pool_path=args.train_pool_path,
        sample_size=args.sample_size,
        n_splits=args.n_splits,
        random_state=args.random_state,
    )
    args.csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(payload["rows"]).to_csv(args.csv_path, index=False)
    save_json(payload, args.json_path)
    print(f"Saved CSV: {args.csv_path}")
    print(f"Saved JSON: {args.json_path}")


if __name__ == "__main__":
    main()
