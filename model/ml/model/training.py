from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from model.ml.model.evaluate import compute_regression_metrics
from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.persistence import save_model_bundle
from model.ml.model.utils import RANDOM_STATE

try:
    from catboost import CatBoostRegressor
except ImportError:  # pragma: no cover - optional dependency
    CatBoostRegressor = None


def train_validation_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.2,
    random_state: int = RANDOM_STATE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    return train_test_split(X, y, test_size=test_size, random_state=random_state)


def _build_baseline_pipeline(feature_config: FeatureConfig) -> Pipeline:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    min_frequency=20,
                    sparse_output=False,
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, feature_config.numerical_features),
            ("cat", categorical_pipeline, feature_config.categorical_features),
        ]
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", LinearRegression()),
        ]
    )


def _fit_log_target_model(model: Any, X_train: pd.DataFrame, y_train: pd.Series, **fit_kwargs: Any) -> Any:
    log_target = np.log1p(y_train)
    model.fit(X_train, log_target, **fit_kwargs)
    return model


def _predict_log_target_model(model: Any, X: pd.DataFrame) -> np.ndarray:
    predictions = np.expm1(model.predict(X))
    return np.clip(predictions, a_min=0.0, a_max=None)


def train_baseline_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_valid: pd.DataFrame,
    y_valid: pd.Series,
    feature_config: FeatureConfig,
) -> dict[str, Any]:
    model = _build_baseline_pipeline(feature_config)
    model = _fit_log_target_model(model, X_train, y_train)
    predictions = _predict_log_target_model(model, X_valid)
    metrics = compute_regression_metrics(y_valid, predictions)

    return {
        "model_name": "linear_regression_baseline",
        "model": model,
        "predictions": predictions,
        "metrics": metrics,
    }


def cross_validate_baseline(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: FeatureConfig,
    n_splits: int = 3,
) -> dict[str, float]:
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    fold_metrics: list[dict[str, float]] = []

    for train_idx, valid_idx in splitter.split(X, y):
        model = _build_baseline_pipeline(feature_config)
        X_train, X_valid = X.iloc[train_idx], X.iloc[valid_idx]
        y_train, y_valid = y.iloc[train_idx], y.iloc[valid_idx]
        _fit_log_target_model(model, X_train, y_train)
        predictions = _predict_log_target_model(model, X_valid)
        fold_metrics.append(compute_regression_metrics(y_valid, predictions))

    return {
        f"{metric}_mean": float(np.mean([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    } | {
        f"{metric}_std": float(np.std([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    }


def _build_catboost_model() -> Any:
    if CatBoostRegressor is None:
        raise ImportError("catboost is not installed.")

    return CatBoostRegressor(
        loss_function="RMSE",
        eval_metric="RMSE",
        learning_rate=0.05,
        depth=8,
        iterations=800,
        l2_leaf_reg=5.0,
        random_seed=RANDOM_STATE,
        verbose=False,
        allow_writing_files=False,
    )


def _prepare_catboost_frame(
    frame: pd.DataFrame,
    feature_config: FeatureConfig,
) -> pd.DataFrame:
    cat_frame = frame.copy()
    for column in feature_config.categorical_features:
        cat_frame[column] = cat_frame[column].fillna("missing").astype(str)
    return cat_frame


def train_catboost_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_valid: pd.DataFrame,
    y_valid: pd.Series,
    feature_config: FeatureConfig,
) -> dict[str, Any]:
    model = _build_catboost_model()
    X_train_cat = _prepare_catboost_frame(X_train, feature_config)
    X_valid_cat = _prepare_catboost_frame(X_valid, feature_config)
    log_y_train = np.log1p(y_train)
    log_y_valid = np.log1p(y_valid)

    model.fit(
        X_train_cat,
        log_y_train,
        cat_features=feature_config.categorical_features,
        eval_set=(X_valid_cat, log_y_valid),
        use_best_model=True,
        early_stopping_rounds=50,
    )

    predictions = _predict_log_target_model(model, X_valid_cat)
    metrics = compute_regression_metrics(y_valid, predictions)

    feature_importance = pd.DataFrame(
        {
            "feature": X_train_cat.columns,
            "importance": model.get_feature_importance(),
        }
    ).sort_values("importance", ascending=False, ignore_index=True)

    return {
        "model_name": "catboost_regressor",
        "model": model,
        "predictions": predictions,
        "metrics": metrics,
        "feature_importance": feature_importance,
    }


def cross_validate_catboost(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: FeatureConfig,
    n_splits: int = 3,
) -> dict[str, float]:
    if CatBoostRegressor is None:
        return {}

    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    fold_metrics: list[dict[str, float]] = []

    for train_idx, valid_idx in splitter.split(X, y):
        model = _build_catboost_model()
        X_train, X_valid = X.iloc[train_idx], X.iloc[valid_idx]
        y_train, y_valid = y.iloc[train_idx], y.iloc[valid_idx]
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
        fold_metrics.append(compute_regression_metrics(y_valid, predictions))

    return {
        f"{metric}_mean": float(np.mean([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    } | {
        f"{metric}_std": float(np.std([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    }


def choose_best_model(model_results: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        model_results,
        key=lambda item: (item["metrics"]["rmse"], item["metrics"]["mae"]),
    )


def fit_best_model_on_full_data(
    best_model_name: str,
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: FeatureConfig,
) -> Any:
    if best_model_name == "linear_regression_baseline":
        model = _build_baseline_pipeline(feature_config)
        return _fit_log_target_model(model, X, y)

    model = _build_catboost_model()
    X_cat = _prepare_catboost_frame(X, feature_config)
    model.fit(X_cat, np.log1p(y), cat_features=feature_config.categorical_features, verbose=False)
    return model
