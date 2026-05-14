from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from model.ml.model.evaluate import compute_regression_metrics
from model.ml.model.feature_schema import (
    NEW_DATASET_REQUIRED_COLUMNS,
    RUSSIA2021_BASE_CURRENCY,
    RUSSIA2021_CATEGORICAL_FEATURES,
    RUSSIA2021_DATASET_NAME,
    RUSSIA2021_MODEL_FEATURE_COLUMNS,
    RUSSIA2021_SOURCE_COLUMNS,
    RUSSIA2021_TARGET_COLUMN,
    russia2021_feature_config,
)
from model.ml.model.category_normalization import CANONICAL_CATEGORY_VALUES, normalize_category_frame
from model.ml.model.normalization import create_model_features, fill_categorical_features_for_catboost
from model.ml.model.market_bounds import compute_market_bounds
from model.ml.model.persistence import TARGET_TRANSFORM_LOG, save_model_bundle
from model.ml.model.readiness import save_readiness_manifest
from model.ml.model.settings import ARTIFACTS_DIR, RAW_DATA_DIR, REPORTS_DIR
from model.ml.model.training import CatBoostRegressor
from model.ml.model.utils import RANDOM_STATE, ensure_directory, save_json


DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH = RAW_DATA_DIR / "russia_real_estate_2021.csv"
DEFAULT_RUSSIA2021_OUTPUT_NAME = "best_model_russia2021.joblib"
DEFAULT_RUSSIA2021_PREPARED_DIR_NAME = "russia2021_prepared"
DEFAULT_RUSSIA2021_CHUNK_SIZE = 200_000
DEFAULT_RUSSIA2021_VALIDATION_SIZE = 0.2
MARKET_BOUNDS_MAX_SAMPLE_ROWS = 750_000
RUSSIA2021_LOG_TARGET_COLUMN = "target_log_price"
RUSSIA2021_LOG_PRICE_PER_M2_TARGET_COLUMN = "target_log_price_per_m2"
RUSSIA2021_TOTAL_POOL_COLUMNS = [RUSSIA2021_LOG_TARGET_COLUMN] + RUSSIA2021_MODEL_FEATURE_COLUMNS
RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS = [
    RUSSIA2021_LOG_PRICE_PER_M2_TARGET_COLUMN,
    *RUSSIA2021_MODEL_FEATURE_COLUMNS,
]
RUSSIA2021_POOL_COLUMNS = RUSSIA2021_TOTAL_POOL_COLUMNS
RUSSIA2021_MODEL_CANDIDATES = ("total_price", "price_per_m2")


@dataclass(frozen=True)
class Russia2021TrainingConfig:
    data_path: Path = DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH
    source_url: str | None = None
    source_dataset_name: str = RUSSIA2021_DATASET_NAME
    source_split: str = "train"
    force_download: bool = False
    artifacts_dir: Path = ARTIFACTS_DIR
    reports_dir: Path = REPORTS_DIR
    output_model_name: str = DEFAULT_RUSSIA2021_OUTPUT_NAME
    prepared_dir_name: str = DEFAULT_RUSSIA2021_PREPARED_DIR_NAME
    chunk_size: int = DEFAULT_RUSSIA2021_CHUNK_SIZE
    validation_size: float = DEFAULT_RUSSIA2021_VALIDATION_SIZE
    random_state: int = RANDOM_STATE
    max_rows: int | None = None
    target_currency: str = RUSSIA2021_BASE_CURRENCY
    iterations: int = 1000
    learning_rate: float = 0.05
    depth: int = 8
    l2_leaf_reg: float = 5.0
    early_stopping_rounds: int = 50


def resolve_russia2021_source_url(explicit_url: str | None = None) -> str | None:
    return explicit_url or os.getenv("RUSSIA2021_DATA_URL")


def download_russia2021_dataset(
    destination_path: Path,
    source_url: str | None,
    force: bool = False,
    chunk_size: int = 1024 * 1024,
) -> Path:
    if destination_path.exists() and not force:
        return destination_path
    if not source_url:
        raise FileNotFoundError(
            "Файл датасета Russia_Real_Estate_2021 не найден. "
            "Передайте --russia-data-path или задайте --russia-data-url/RUSSIA2021_DATA_URL."
        )

    ensure_directory(destination_path.parent)
    response = requests.get(source_url, stream=True, timeout=120)
    response.raise_for_status()

    with destination_path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)

    return destination_path


def validate_russia2021_schema(columns: list[str] | pd.Index) -> None:
    available = set(columns)
    missing = [column for column in NEW_DATASET_REQUIRED_COLUMNS if column not in available]
    if missing:
        raise ValueError(
            "Некорректная схема датасета Russia_Real_Estate_2021. "
            f"Отсутствуют колонки: {', '.join(missing)}."
        )


def read_russia2021_header(dataset_path: Path) -> list[str]:
    header = pd.read_csv(dataset_path, nrows=0)
    return list(header.columns)


def _available_source_columns(columns: list[str] | pd.Index) -> list[str]:
    available = set(columns)
    return [column for column in RUSSIA2021_SOURCE_COLUMNS if column in available]


def _stream_hf_dataset_chunks(config: Russia2021TrainingConfig):
    try:
        from model.ml.model.datasets import load_dataset
    except ImportError as exc:
        raise ImportError(
            "Для потоковой загрузки daniilakk/Russia_Real_Estate_2021 установите пакет datasets."
        ) from exc

    dataset = load_dataset(
        config.source_dataset_name,
        split=config.source_split,
        streaming=True,
    )
    iterator = iter(dataset)
    try:
        first_row = next(iterator)
    except StopIteration as exc:
        raise ValueError("Поток датасета Russia_Real_Estate_2021 не содержит строк.") from exc

    validate_russia2021_schema(first_row.keys())
    source_columns = _available_source_columns(first_row.keys())
    rows = [{column: first_row.get(column) for column in source_columns}]

    for row in iterator:
        rows.append({column: row.get(column) for column in source_columns})
        if len(rows) >= config.chunk_size:
            yield pd.DataFrame.from_records(rows)
            rows = []

    if rows:
        yield pd.DataFrame.from_records(rows)


def _csv_dataset_chunks(dataset_path: Path, chunk_size: int):
    header = read_russia2021_header(dataset_path)
    validate_russia2021_schema(header)
    source_columns = _available_source_columns(header)
    yield from pd.read_csv(
        dataset_path,
        usecols=source_columns,
        chunksize=chunk_size,
    )


def _numeric_chunk(raw_chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = raw_chunk.copy()
    for column in RUSSIA2021_SOURCE_COLUMNS:
        if column in chunk.columns:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
    return chunk


def preprocess_russia2021_chunk(raw_chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = _numeric_chunk(raw_chunk)
    chunk = chunk.dropna(subset=NEW_DATASET_REQUIRED_COLUMNS)
    chunk, _ = normalize_category_frame(chunk)
    categories_valid = pd.Series(True, index=chunk.index)
    if "building_type" in chunk.columns:
        categories_valid &= chunk["building_type"].isin(CANONICAL_CATEGORY_VALUES["building_type"])
    if "object_type" in chunk.columns:
        categories_valid &= chunk["object_type"].isin(CANONICAL_CATEGORY_VALUES["object_type"])

    price_per_m2 = chunk[RUSSIA2021_TARGET_COLUMN] / chunk["area"].replace({0: np.nan})
    chunk = chunk[
        (chunk[RUSSIA2021_TARGET_COLUMN] > 0)
        & (chunk["rooms"] >= -1)
        & (chunk["rooms"] <= 20)
        & (chunk["area"] >= 10)
        & (chunk["area"] <= 500)
        & (chunk["kitchen_area"] >= 0)
        & (chunk["kitchen_area"] <= chunk["area"])
        & (chunk["level"] > 0)
        & (chunk["levels"] > 0)
        & (chunk["level"] <= chunk["levels"])
        & (chunk["levels"] <= 100)
        & (chunk["rooms"].le(np.maximum(1, np.floor(chunk["area"] / 8))))
        & price_per_m2.between(
            price_per_m2.quantile(0.005),
            price_per_m2.quantile(0.995),
            inclusive="both",
        )
        & categories_valid
    ].copy()
    if chunk.empty:
        return chunk

    chunk[RUSSIA2021_LOG_TARGET_COLUMN] = np.log(chunk[RUSSIA2021_TARGET_COLUMN].astype(float))
    chunk[RUSSIA2021_LOG_PRICE_PER_M2_TARGET_COLUMN] = np.log(
        (chunk[RUSSIA2021_TARGET_COLUMN].astype(float) / chunk["area"].astype(float))
    )
    feature_config = russia2021_feature_config()
    feature_frame = create_model_features(chunk, feature_config)
    feature_frame = fill_categorical_features_for_catboost(feature_frame, feature_config.categorical_features)
    return pd.concat(
        [
            chunk.loc[
                :,
                [RUSSIA2021_LOG_TARGET_COLUMN, RUSSIA2021_LOG_PRICE_PER_M2_TARGET_COLUMN],
            ].reset_index(drop=True),
            feature_frame.reset_index(drop=True),
        ],
        axis=1,
    )


def _write_pool_header(path: Path, columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)


def _append_pool_rows(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, mode="a", header=False, index=False)


def _write_column_description(path: Path, columns: list[str]) -> None:
    with path.open("w", encoding="utf-8") as file:
        file.write("0\tLabel\n")
        categorical_features = set(RUSSIA2021_CATEGORICAL_FEATURES)
        for index, column in enumerate(columns[1:], start=1):
            column_type = "Categ" if column in categorical_features else "Num"
            file.write(f"{index}\t{column_type}\n")


def prepare_russia2021_training_files(config: Russia2021TrainingConfig) -> dict[str, Any]:
    source_url = resolve_russia2021_source_url(config.source_url)
    if config.data_path.exists() or source_url:
        dataset_path = download_russia2021_dataset(
            config.data_path,
            source_url,
            force=config.force_download,
        )
        chunk_iterator = _csv_dataset_chunks(dataset_path, config.chunk_size)
        dataset_source = str(dataset_path)
    else:
        dataset_path = None
        chunk_iterator = _stream_hf_dataset_chunks(config)
        dataset_source = f"{config.source_dataset_name}:{config.source_split}"

    prepared_dir = ensure_directory(config.artifacts_dir / config.prepared_dir_name)
    train_path = prepared_dir / "train_pool.csv"
    valid_path = prepared_dir / "valid_pool.csv"
    train_price_per_m2_path = prepared_dir / "train_pool_price_per_m2.csv"
    valid_price_per_m2_path = prepared_dir / "valid_pool_price_per_m2.csv"
    cd_path = prepared_dir / "columns.cd"
    cd_price_per_m2_path = prepared_dir / "columns_price_per_m2.cd"
    _write_pool_header(train_path, RUSSIA2021_TOTAL_POOL_COLUMNS)
    _write_pool_header(valid_path, RUSSIA2021_TOTAL_POOL_COLUMNS)
    _write_pool_header(train_price_per_m2_path, RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS)
    _write_pool_header(valid_price_per_m2_path, RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS)
    _write_column_description(cd_path, RUSSIA2021_TOTAL_POOL_COLUMNS)
    _write_column_description(cd_price_per_m2_path, RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS)

    rng = np.random.default_rng(config.random_state)
    rows_read = 0
    rows_after_preprocessing = 0
    train_rows = 0
    valid_rows = 0
    remaining_rows = config.max_rows

    for raw_chunk in chunk_iterator:
        rows_read += len(raw_chunk)
        prepared_chunk = preprocess_russia2021_chunk(raw_chunk)
        if prepared_chunk.empty:
            continue
        if remaining_rows is not None:
            if remaining_rows <= 0:
                break
            prepared_chunk = prepared_chunk.head(remaining_rows)
            remaining_rows -= len(prepared_chunk)
        rows_after_preprocessing += len(prepared_chunk)

        valid_mask = rng.random(len(prepared_chunk)) < config.validation_size
        valid_chunk = prepared_chunk.loc[valid_mask]
        train_chunk = prepared_chunk.loc[~valid_mask]
        if not train_chunk.empty:
            _append_pool_rows(train_path, train_chunk.loc[:, RUSSIA2021_TOTAL_POOL_COLUMNS])
            _append_pool_rows(
                train_price_per_m2_path,
                train_chunk.loc[:, RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS],
            )
            train_rows += len(train_chunk)
        if not valid_chunk.empty:
            _append_pool_rows(valid_path, valid_chunk.loc[:, RUSSIA2021_TOTAL_POOL_COLUMNS])
            _append_pool_rows(
                valid_price_per_m2_path,
                valid_chunk.loc[:, RUSSIA2021_PRICE_PER_M2_POOL_COLUMNS],
            )
            valid_rows += len(valid_chunk)

    if train_rows == 0 or valid_rows == 0:
        raise ValueError(
            "После предобработки не осталось строк для обучения или валидации. "
            "Проверьте входной датасет и validation_size."
        )

    return {
        "dataset_path": str(dataset_path) if dataset_path is not None else None,
        "dataset_source": dataset_source,
        "train_path": str(train_path),
        "valid_path": str(valid_path),
        "price_per_m2_train_path": str(train_price_per_m2_path),
        "price_per_m2_valid_path": str(valid_price_per_m2_path),
        "column_description_path": str(cd_path),
        "price_per_m2_column_description_path": str(cd_price_per_m2_path),
        "rows_read": rows_read,
        "rows_after_preprocessing": rows_after_preprocessing,
        "train_rows": train_rows,
        "valid_rows": valid_rows,
    }


def _build_russia2021_model(config: Russia2021TrainingConfig) -> Any:
    if CatBoostRegressor is None:
        raise ImportError("catboost is not installed.")

    return CatBoostRegressor(
        loss_function="RMSE",
        eval_metric="RMSE",
        learning_rate=config.learning_rate,
        depth=config.depth,
        iterations=config.iterations,
        l2_leaf_reg=config.l2_leaf_reg,
        random_seed=config.random_state,
        verbose=False,
        allow_writing_files=False,
    )


def _load_validation_target_frame(valid_path: str, target_column: str) -> pd.DataFrame:
    return pd.read_csv(
        valid_path,
        usecols=[
            target_column,
            "area",
            "rooms",
            "object_type",
            "building_type",
            "region",
        ],
    )


def compute_russia2021_metrics(
    model: Any,
    valid_pool: Any,
    *,
    valid_path: str,
    target_column: str,
    prediction_target: str,
) -> dict[str, float]:
    log_predictions = np.asarray(model.predict(valid_pool), dtype=float)
    target_frame = _load_validation_target_frame(valid_path, target_column)
    log_target = target_frame[target_column].to_numpy(dtype=float)
    if prediction_target == "price_per_m2":
        area = target_frame["area"].to_numpy(dtype=float)
        price_predictions = np.exp(log_predictions) * area
        price_target = np.exp(log_target) * area
    else:
        price_predictions = np.exp(log_predictions)
        price_target = np.exp(log_target)
    original_scale_metrics = compute_regression_metrics(pd.Series(price_target), price_predictions)
    rmse_log = float(np.sqrt(np.mean(np.square(log_predictions - log_target))))
    return {
        "rmse_log": rmse_log,
        "mae_price": original_scale_metrics["mae"],
        "rmse_price": original_scale_metrics["rmse"],
        "mape_price": original_scale_metrics["mape"],
        "r2_price": original_scale_metrics["r2"],
    }


def build_segment_metrics_report(
    *,
    model: Any,
    valid_pool: Any,
    valid_path: str,
    target_column: str,
    prediction_target: str,
) -> list[dict[str, Any]]:
    log_predictions = np.asarray(model.predict(valid_pool), dtype=float)
    target_frame = _load_validation_target_frame(valid_path, target_column)
    log_target = target_frame[target_column].to_numpy(dtype=float)
    area = target_frame["area"].to_numpy(dtype=float)

    if prediction_target == "price_per_m2":
        y_pred = np.exp(log_predictions) * area
        y_true = np.exp(log_target) * area
    else:
        y_pred = np.exp(log_predictions)
        y_true = np.exp(log_target)

    report_frame = target_frame.copy()
    report_frame["y_true"] = y_true
    report_frame["y_pred"] = y_pred
    report_frame["price_per_m2"] = report_frame["y_true"] / report_frame["area"].replace({0: np.nan})
    report_frame["area_bucket"] = pd.cut(
        report_frame["area"],
        bins=[0, 20, 40, 70, np.inf],
        labels=["<20", "20-40", "40-70", "70+"],
        right=False,
    ).astype(str)
    report_frame["small_area_segment"] = np.where(report_frame["area"] < 20, "very_small", "regular")
    report_frame["rooms_segment"] = report_frame["rooms"].astype(str)
    if len(report_frame) >= 4:
        report_frame["price_bucket"] = pd.qcut(
            report_frame["price_per_m2"].rank(method="first"),
            q=4,
            labels=["q1", "q2", "q3", "q4"],
        ).astype(str)
    else:
        report_frame["price_bucket"] = "all"

    reports: list[dict[str, Any]] = []
    for segment_name in [
        "region",
        "area_bucket",
        "rooms_segment",
        "object_type",
        "price_bucket",
        "small_area_segment",
    ]:
        for segment_value, group in report_frame.groupby(segment_name, dropna=False):
            if group.empty:
                continue
            metrics = compute_regression_metrics(group["y_true"], group["y_pred"].to_numpy())
            reports.append(
                {
                    "segment_name": segment_name,
                    "segment_value": str(segment_value),
                    "rows": int(len(group)),
                    "metrics": metrics,
                }
            )
    return reports


def _train_candidate_from_pool(
    *,
    config: Russia2021TrainingConfig,
    prepared: dict[str, Any],
    prediction_target: str,
) -> dict[str, Any]:
    from catboost import Pool

    if prediction_target == "price_per_m2":
        train_path = prepared["price_per_m2_train_path"]
        valid_path = prepared["price_per_m2_valid_path"]
        column_description_path = prepared["price_per_m2_column_description_path"]
        target_column = RUSSIA2021_LOG_PRICE_PER_M2_TARGET_COLUMN
        model_name = "catboost_regressor_russia2021_price_per_m2"
    else:
        train_path = prepared["train_path"]
        valid_path = prepared["valid_path"]
        column_description_path = prepared["column_description_path"]
        target_column = RUSSIA2021_LOG_TARGET_COLUMN
        model_name = "catboost_regressor_russia2021_total_price"

    train_pool = Pool(
        data=train_path,
        column_description=column_description_path,
        delimiter=",",
        has_header=True,
    )
    valid_pool = Pool(
        data=valid_path,
        column_description=column_description_path,
        delimiter=",",
        has_header=True,
    )

    model = _build_russia2021_model(config)
    model.fit(
        train_pool,
        eval_set=valid_pool,
        use_best_model=True,
        early_stopping_rounds=config.early_stopping_rounds,
    )
    metrics = compute_russia2021_metrics(
        model,
        valid_pool,
        valid_path=valid_path,
        target_column=target_column,
        prediction_target=prediction_target,
    )
    segment_metrics = build_segment_metrics_report(
        model=model,
        valid_pool=valid_pool,
        valid_path=valid_path,
        target_column=target_column,
        prediction_target=prediction_target,
    )
    return {
        "model_name": model_name,
        "model": model,
        "metrics": metrics,
        "segment_metrics": segment_metrics,
        "prediction_target": prediction_target,
        "target_log_column": target_column,
        "train_path": train_path,
        "valid_path": valid_path,
        "column_description_path": column_description_path,
    }


def choose_russia2021_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        candidates,
        key=lambda item: (
            item["metrics"]["mape_price"],
            item["metrics"]["rmse_log"],
            item["metrics"]["mae_price"],
        ),
    )


def train_russia2021_model(config: Russia2021TrainingConfig) -> dict[str, Any]:
    prepared = prepare_russia2021_training_files(config)
    candidates = [
        _train_candidate_from_pool(
            config=config,
            prepared=prepared,
            prediction_target=prediction_target,
        )
        for prediction_target in RUSSIA2021_MODEL_CANDIDATES
    ]
    best_candidate = choose_russia2021_candidate(candidates)
    return {
        **best_candidate,
        "prepared": prepared,
        "candidates": candidates,
    }


def _compute_market_bounds_from_prepared_train(prepared: dict[str, Any]) -> dict[str, Any]:
    bounds_frames: list[pd.DataFrame] = []
    train_rows = max(int(prepared.get("train_rows") or 0), 1)
    sample_fraction = min(1.0, MARKET_BOUNDS_MAX_SAMPLE_ROWS / train_rows)
    random_state = RANDOM_STATE
    for chunk in pd.read_csv(
        prepared["train_path"],
        usecols=[
            RUSSIA2021_LOG_TARGET_COLUMN,
            "area",
            "region",
            "object_type",
            "building_type",
        ],
        chunksize=500_000,
    ):
        if sample_fraction < 1.0:
            chunk = chunk.sample(frac=sample_fraction, random_state=random_state)
            random_state += 1
        chunk = chunk.copy()
        chunk["price"] = np.exp(chunk[RUSSIA2021_LOG_TARGET_COLUMN].astype(float))
        bounds_frames.append(chunk[["price", "area", "region", "object_type", "building_type"]])
    if not bounds_frames:
        return {}
    bounds_source = pd.concat(bounds_frames, ignore_index=True)
    bounds = compute_market_bounds(bounds_source, price_column="price", area_column="area")
    bounds["sample_rows"] = int(len(bounds_source))
    bounds["train_rows"] = int(train_rows)
    bounds["sampling"] = "full" if sample_fraction >= 1.0 else "deterministic_chunk_sample"
    return bounds


def _collect_region_values(train_path: str) -> list[str]:
    values: set[str] = set()
    for chunk in pd.read_csv(train_path, usecols=["region"], chunksize=500_000):
        values.update(chunk["region"].dropna().astype(str).unique().tolist())
    return sorted(values)


def _candidate_report_payload(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "model_name": candidate["model_name"],
            "prediction_target": candidate["prediction_target"],
            "metrics": candidate["metrics"],
            "target_log_column": candidate["target_log_column"],
        }
        for candidate in candidates
    ]


def run_russia2021_pipeline(config: Russia2021TrainingConfig) -> Path:
    ensure_directory(config.artifacts_dir)
    ensure_directory(config.reports_dir)
    result = train_russia2021_model(config)
    feature_config = russia2021_feature_config()
    market_bounds = _compute_market_bounds_from_prepared_train(result["prepared"])
    metadata = {
        "dataset_name": RUSSIA2021_DATASET_NAME,
        "target_formula": (
            "F(x)=log(price_per_m2)"
            if result["prediction_target"] == "price_per_m2"
            else "F(x)=log(price)"
        ),
        "target_column": RUSSIA2021_TARGET_COLUMN,
        "prediction_target": result["prediction_target"],
        "feature_columns": RUSSIA2021_MODEL_FEATURE_COLUMNS,
        "categorical_features": RUSSIA2021_CATEGORICAL_FEATURES,
        "category_values": {
            "building_type": ["unknown", "other", "panel", "monolith", "brick", "block", "wooden"],
            "object_type": ["secondary", "new"],
            "region": _collect_region_values(result["prepared"]["train_path"]),
        },
        "market_bounds": market_bounds,
        "base_currency": config.target_currency.upper(),
        "training_rows": result["prepared"]["train_rows"],
        "validation_rows": result["prepared"]["valid_rows"],
        "rows_read": result["prepared"]["rows_read"],
        "rows_after_preprocessing": result["prepared"]["rows_after_preprocessing"],
        "dataset_source": result["prepared"]["dataset_source"],
        "validation_size": config.validation_size,
        "random_state": config.random_state,
        "max_rows": config.max_rows,
    }
    output_path = save_model_bundle(
        model=result["model"],
        model_name=result["model_name"],
        feature_config=feature_config,
        metrics=result["metrics"],
        output_path=config.artifacts_dir / config.output_model_name,
        target_transform=TARGET_TRANSFORM_LOG,
        base_currency=config.target_currency,
        metadata=metadata,
    )
    candidates_payload = _candidate_report_payload(result["candidates"])
    save_json(
        {
            "model_name": result["model_name"],
            "metrics": result["metrics"],
            "segment_metrics": result["segment_metrics"],
            "metadata": metadata,
            "prepared_files": result["prepared"],
            "candidates": candidates_payload,
            "artifact_path": str(output_path),
        },
        config.reports_dir / "russia2021_training_report.json",
    )
    save_json(
        {
            "model_name": result["model_name"],
            "prediction_target": result["prediction_target"],
            "segments": result["segment_metrics"],
        },
        config.reports_dir / "russia2021_segment_metrics_report.json",
    )
    save_json(market_bounds, config.reports_dir / "russia2021_market_bounds.json")
    save_readiness_manifest(
        artifact_path=output_path,
        model_name=result["model_name"],
        metrics=result["metrics"],
        metadata=metadata,
        candidates=candidates_payload,
        status="active",
        output_path=config.artifacts_dir / "model_readiness.json",
    )
    return output_path


def build_russia2021_config_from_args(args: argparse.Namespace) -> Russia2021TrainingConfig:
    if str(args.russia_target_currency).upper() != "RUB":
        raise ValueError("Новый training pipeline поддерживает только RUB.")
    return Russia2021TrainingConfig(
        data_path=args.russia_data_path,
        source_url=args.russia_data_url,
        source_dataset_name=args.russia_source_dataset,
        source_split=args.russia_source_split,
        force_download=args.russia_force_download,
        artifacts_dir=args.artifacts_dir,
        reports_dir=args.reports_dir,
        output_model_name=args.russia_output_model_name,
        chunk_size=args.russia_chunk_size,
        validation_size=args.russia_validation_size,
        random_state=args.russia_random_state,
        max_rows=args.russia_max_rows,
        target_currency=args.russia_target_currency,
        iterations=args.russia_iterations,
        learning_rate=args.russia_learning_rate,
        depth=args.russia_depth,
        l2_leaf_reg=args.russia_l2_leaf_reg,
        early_stopping_rounds=args.russia_early_stopping_rounds,
    )
