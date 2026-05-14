from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.ml.model.persistence import inverse_transform_predictions, load_model_bundle


DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "best_model_russia2021.joblib"
DEFAULT_TRAIN_POOL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "train_pool.csv"
DEFAULT_VALID_POOL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "valid_pool.csv"
DEFAULT_CD_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "columns.cd"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"
TARGET_LOG_COLUMN = "target_log_price"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def save_json(payload: dict[str, Any], path: Path) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as file:
        json.dump(to_jsonable(payload), file, ensure_ascii=False, indent=2)


def load_russia2021_bundle(model_path: Path = DEFAULT_MODEL_PATH):
    return load_model_bundle(model_path)


def feature_columns(bundle: Any) -> list[str]:
    return list(bundle.feature_config.numerical_features) + list(bundle.feature_config.categorical_features)


def catboost_params_from_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "get_params"):
        return dict(model.get_params())
    return {}


def catboost_all_params_subset(model: Any) -> dict[str, Any]:
    if not hasattr(model, "get_all_params"):
        return {}
    params = model.get_all_params()
    keys = [
        "learning_rate",
        "depth",
        "iterations",
        "loss_function",
        "eval_metric",
        "l2_leaf_reg",
        "random_seed",
        "od_type",
        "od_wait",
        "use_best_model",
        "bootstrap_type",
    ]
    return {key: params.get(key) for key in keys}


def read_pool_frame(
    path: Path,
    *,
    sample_size: int | None = None,
    random_state: int = 42,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    if sample_size is None:
        return pd.read_csv(path, usecols=columns)
    frame = pd.read_csv(path, usecols=columns)
    if len(frame) <= sample_size:
        return frame
    return frame.sample(n=sample_size, random_state=random_state).reset_index(drop=True)


def split_xy(frame: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, np.ndarray]:
    x_frame = frame.loc[:, features].copy()
    y_true = np.exp(pd.to_numeric(frame[TARGET_LOG_COLUMN], errors="coerce").to_numpy(dtype=float))
    return x_frame, y_true


def prepare_catboost_frame(frame: pd.DataFrame, categorical_features: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in categorical_features:
        if column in result.columns:
            result[column] = result[column].fillna("missing").astype(str)
    return result


def predict_bundle_on_frame(bundle: Any, frame: pd.DataFrame) -> np.ndarray:
    features = feature_columns(bundle)
    x_frame = prepare_catboost_frame(frame.loc[:, features], bundle.feature_config.categorical_features)
    raw_predictions = bundle.model.predict(x_frame)
    return inverse_transform_predictions(raw_predictions, bundle.target_transform)


def compute_metrics(y_true: np.ndarray | pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_array = np.asarray(y_true, dtype=float)
    y_pred_array = np.asarray(y_pred, dtype=float)
    non_zero_mask = y_true_array != 0
    mape_fraction = float(
        np.mean(np.abs((y_true_array[non_zero_mask] - y_pred_array[non_zero_mask]) / y_true_array[non_zero_mask]))
    )
    return {
        "MAE": float(mean_absolute_error(y_true_array, y_pred_array)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true_array, y_pred_array))),
        "MAPE": mape_fraction * 100.0,
        "R²": float(r2_score(y_true_array, y_pred_array)),
        "mape_fraction": mape_fraction,
    }


def train_catboost(
    x_train: pd.DataFrame,
    y_train_log: np.ndarray,
    x_valid: pd.DataFrame,
    y_valid_log: np.ndarray,
    categorical_features: list[str],
    params: dict[str, Any],
    *,
    early_stopping_rounds: int = 50,
) -> CatBoostRegressor:
    model = CatBoostRegressor(**params)
    model.fit(
        prepare_catboost_frame(x_train, categorical_features),
        y_train_log,
        cat_features=[feature for feature in categorical_features if feature in x_train.columns],
        eval_set=(
            prepare_catboost_frame(x_valid, categorical_features),
            y_valid_log,
        ),
        use_best_model=True,
        early_stopping_rounds=early_stopping_rounds,
        verbose=False,
    )
    return model


def evaluate_trained_model(
    model: Any,
    x_valid: pd.DataFrame,
    y_valid: np.ndarray,
    categorical_features: list[str],
) -> dict[str, float]:
    raw_predictions = model.predict(prepare_catboost_frame(x_valid, categorical_features))
    predictions = np.exp(np.asarray(raw_predictions, dtype=float))
    return compute_metrics(y_valid, predictions)


def make_pool(path: Path = DEFAULT_VALID_POOL_PATH, cd_path: Path = DEFAULT_CD_PATH) -> Pool:
    return Pool(data=str(path), column_description=str(cd_path), delimiter=",", has_header=True)
