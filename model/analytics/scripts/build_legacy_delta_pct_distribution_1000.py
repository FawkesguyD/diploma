from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", "/tmp/real_estate_analytics_matplotlib")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.analytics.config import AnalyticsConfig
from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH, load_dataset_frame
from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.normalization import create_model_features
from model.ml.model.persistence import inverse_transform_predictions, resolve_target_transform
from model.ml.model.training_preprocessing import clean_dataset
from model.shared.db.session import create_db_engine


DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "linear_regression_baseline.joblib"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analytics" / "reports"
DEFAULT_PREDICTIONS_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_predictions_1000.csv"
DEFAULT_STATS_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_stats_1000.json"
DEFAULT_SUMMARY_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_summary_1000.md"
DEFAULT_HISTOGRAM_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_distribution_1000.png"
SYNTHETIC_CONTROL_PATH = PROJECT_ROOT / "reports" / "synthetic_control_objects_1000.csv"
OLD_CONTROL_SAMPLE_PATH = PROJECT_ROOT / "analytics" / "reports" / "control_sample_predictions.csv"
PREPARED_VALID_POOL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "valid_pool.csv"
TARGET_SAMPLE_SIZE = 1000
RANDOM_STATE = 42
USD_TO_RUB_RATE = 90.0


@dataclass(frozen=True)
class SourceCandidate:
    name: str
    priority: int
    frame: pd.DataFrame
    description: str
    listing_price_column: str
    listing_currency: str
    is_old_32_row_control_sample: bool = False


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def _first_existing(frame: pd.DataFrame, columns: list[str]) -> str | None:
    for column in columns:
        if column in frame.columns:
            return column
    return None


def load_legacy_payload(model_path: Path) -> dict[str, Any]:
    payload = joblib.load(model_path)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected dict bundle at {model_path}, got {type(payload).__name__}.")
    if "model" not in payload or "feature_config" not in payload:
        raise KeyError("Legacy artifact must contain 'model' and 'feature_config'.")
    return payload


def feature_config_from_payload(payload: dict[str, Any]) -> FeatureConfig:
    return FeatureConfig(**payload["feature_config"])


def try_load_postgres_control_objects() -> tuple[SourceCandidate | None, dict[str, Any]]:
    config = AnalyticsConfig.from_env()
    query = """
        select
          listing_id,
          listing_price,
          listing_currency,
          area,
          area as total_area_m2,
          rooms,
          kitchen_area,
          kitchen_area as kitchen_area_m2,
          level,
          level as floor,
          levels,
          levels as total_floors,
          city,
          district,
          region,
          building_type,
          condition,
          seller_type,
          object_type,
          latitude,
          longitude
        from analytics_control_objects
        order by sample_seed asc, sample_rank asc
    """
    engine = create_db_engine(config.database_url)
    try:
        with engine.connect() as connection:
            exists = connection.execute(text("select to_regclass('public.analytics_control_objects')")).scalar()
            if not exists:
                return None, {"available": False, "reason": "table_missing"}
            frame = pd.read_sql_query(text(query), connection)
    except Exception as exc:
        return None, {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        engine.dispose()

    return SourceCandidate(
        name="postgres.analytics_control_objects",
        priority=1,
        frame=frame,
        description="PostgreSQL table analytics_control_objects",
        listing_price_column="listing_price",
        listing_currency="RUB",
    ), {"available": True, "rows": int(len(frame))}


def load_synthetic_control_csv() -> SourceCandidate | None:
    if not SYNTHETIC_CONTROL_PATH.exists():
        return None
    frame = pd.read_csv(SYNTHETIC_CONTROL_PATH)
    if "P_list_synthetic" not in frame.columns:
        return None
    frame = frame.rename(columns={"P_list_synthetic": "listing_price"})
    frame["listing_currency"] = "RUB"
    return SourceCandidate(
        name="reports.synthetic_control_objects_1000",
        priority=2,
        frame=frame,
        description=(
            "reports/synthetic_control_objects_1000.csv; synthetic listing prices from Russia 2021 "
            "ranking benchmark"
        ),
        listing_price_column="listing_price",
        listing_currency="RUB",
    )


def load_raw_listings_dataset(force_download: bool) -> SourceCandidate:
    frame = load_dataset_frame(DEFAULT_LOCAL_DATASET_PATH, force_download=force_download)
    frame["listing_price"] = pd.to_numeric(frame["price_usd"], errors="coerce")
    frame["listing_currency"] = "USD"
    return SourceCandidate(
        name="ml.data.raw.listings",
        priority=3,
        frame=frame,
        description=f"Raw project dataset {DEFAULT_LOCAL_DATASET_PATH}",
        listing_price_column="listing_price",
        listing_currency="USD",
    )


def load_prepared_valid_pool() -> SourceCandidate | None:
    if not PREPARED_VALID_POOL_PATH.exists():
        return None
    frame = pd.read_csv(PREPARED_VALID_POOL_PATH)
    if "target_log_price" not in frame.columns:
        return None
    frame = frame.reset_index(names="valid_pool_row_index")
    frame["listing_id"] = frame["valid_pool_row_index"].map(lambda value: f"russia2021_valid_{int(value):07d}")
    frame["listing_price"] = np.exp(pd.to_numeric(frame["target_log_price"], errors="coerce"))
    frame["listing_currency"] = "RUB"
    return SourceCandidate(
        name="ml.artifacts.russia2021_prepared.valid_pool",
        priority=4,
        frame=frame,
        description=f"Prepared Russia 2021 validation pool {PREPARED_VALID_POOL_PATH}",
        listing_price_column="listing_price",
        listing_currency="RUB",
    )


def load_old_control_sample_csv() -> SourceCandidate | None:
    if not OLD_CONTROL_SAMPLE_PATH.exists():
        return None
    frame = pd.read_csv(OLD_CONTROL_SAMPLE_PATH)
    if "listing_price" not in frame.columns:
        return None
    return SourceCandidate(
        name="analytics.reports.control_sample_predictions",
        priority=99,
        frame=frame,
        description="Old 32-row control sample predictions report; diagnostic only, not used as primary source",
        listing_price_column="listing_price",
        listing_currency="RUB",
        is_old_32_row_control_sample=True,
    )


def load_source_candidates(force_download: bool) -> tuple[list[SourceCandidate], dict[str, Any]]:
    candidates: list[SourceCandidate] = []
    source_audit: dict[str, Any] = {}

    postgres_candidate, postgres_audit = try_load_postgres_control_objects()
    source_audit["postgres.analytics_control_objects"] = postgres_audit
    if postgres_candidate is not None:
        candidates.append(postgres_candidate)

    for loader in (
        load_synthetic_control_csv,
        lambda: load_raw_listings_dataset(force_download),
        load_prepared_valid_pool,
        load_old_control_sample_csv,
    ):
        try:
            candidate = loader()
        except Exception as exc:
            source_audit[getattr(loader, "__name__", "source_loader")] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
            continue
        if candidate is not None:
            candidates.append(candidate)
            source_audit[candidate.name] = {"available": True, "rows": int(len(candidate.frame))}

    return sorted(candidates, key=lambda item: item.priority), source_audit


def normalize_source_frame(candidate: SourceCandidate, feature_config: FeatureConfig) -> pd.DataFrame:
    frame = candidate.frame.copy()

    aliases = {
        "area": "total_area_m2",
        "total_area": "total_area_m2",
        "kitchen_area": "kitchen_area_m2",
        "level": "floor",
        "levels": "total_floors",
        "coordinates_lat": "latitude",
        "coordinates_lng": "longitude",
        "districts": "district",
        "inner_id": "listing_id",
    }
    for source, target in aliases.items():
        if source in frame.columns and target not in frame.columns:
            frame[target] = frame[source]

    if "listing_currency" not in frame.columns:
        frame["listing_currency"] = candidate.listing_currency
    if candidate.listing_price_column != "listing_price" and candidate.listing_price_column in frame.columns:
        frame["listing_price"] = frame[candidate.listing_price_column]
    if "price_usd" in frame.columns and "price" not in frame.columns:
        frame["price"] = frame["price_usd"]

    minimal = frame.copy()
    target_column = feature_config.target_column
    if target_column not in minimal.columns:
        minimal[target_column] = minimal["listing_price"]
    if "listing_price" not in minimal.columns:
        minimal["listing_price"] = minimal[target_column]

    if target_column == "price_usd":
        minimal["price_usd"] = pd.to_numeric(minimal[target_column], errors="coerce")

    try:
        cleaned = clean_dataset(minimal)
    except Exception:
        cleaned = minimal

    return cleaned


def filter_valid_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["listing_price"] = pd.to_numeric(result["listing_price"], errors="coerce")
    result = result.replace([np.inf, -np.inf], np.nan)
    result = result[result["listing_price"].notna() & (result["listing_price"] > 0)]

    area_column = _first_existing(result, ["total_area_m2", "area"])
    if area_column is not None:
        area = pd.to_numeric(result[area_column], errors="coerce")
        result = result[area.notna() & (area > 0)]

    if "listing_id" in result.columns:
        result = result.drop_duplicates(subset=["listing_id"], keep="first")

    result = result.reset_index(drop=True)
    return result


def sample_valid_frame(frame: pd.DataFrame, sample_size: int, random_state: int) -> pd.DataFrame:
    result = frame.copy()
    if len(result) > sample_size:
        result = result.sample(n=sample_size, random_state=random_state).reset_index(drop=True)
    return result


def model_output_currency(payload: dict[str, Any]) -> str:
    base_currency = payload.get("base_currency")
    if base_currency:
        return str(base_currency).upper()
    target_column = str(payload.get("target_column") or payload.get("feature_config", {}).get("target_column") or "")
    if target_column.endswith("_usd"):
        return "USD"
    if target_column in {"price", "listing_price"}:
        return "RUB"
    return "UNKNOWN"


def predict_expected_price(
    payload: dict[str, Any],
    feature_frame: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    raw_predictions = np.asarray(payload["model"].predict(feature_frame), dtype=float)
    target_transform = resolve_target_transform(payload)
    expected = inverse_transform_predictions(raw_predictions, target_transform)
    return raw_predictions, np.asarray(expected, dtype=float), {
        "target_transform": target_transform,
        "inverse_transform": "expm1" if target_transform == "log1p" else "exp" if target_transform == "log" else "identity",
    }


def convert_expected_currency(
    expected: np.ndarray,
    *,
    model_currency: str,
    listing_currency: str,
) -> tuple[np.ndarray, str, float | None, str]:
    model_currency = model_currency.upper()
    listing_currency = listing_currency.upper()
    if model_currency == listing_currency:
        return expected, listing_currency, None, "none"
    if model_currency == "USD" and listing_currency == "RUB":
        return expected * USD_TO_RUB_RATE, "RUB", USD_TO_RUB_RATE, "USD_to_RUB"
    if model_currency == "RUB" and listing_currency == "USD":
        return expected / USD_TO_RUB_RATE, "USD", USD_TO_RUB_RATE, "RUB_to_USD"
    return expected, model_currency, None, "unknown_no_conversion"


def build_feature_audit(frame: pd.DataFrame, feature_config: FeatureConfig, feature_frame: pd.DataFrame) -> dict[str, Any]:
    source_columns = set(frame.columns)
    feature_columns = feature_config.feature_columns
    found = [column for column in feature_columns if column in source_columns]
    derived = [column for column in feature_config.derived_numeric_features if column in feature_columns]
    missing_source = [column for column in feature_columns if column not in source_columns and column not in derived]
    null_counts = {column: int(feature_frame[column].isna().sum()) for column in feature_columns if column in feature_frame}
    return {
        "feature_columns": feature_columns,
        "features_found_in_source": found,
        "derived_features_generated": derived,
        "features_missing_in_source": missing_source,
        "missing_value_fill_policy": {
            "numeric": "sklearn SimpleImputer(strategy='median') inside legacy Pipeline",
            "categorical": "sklearn SimpleImputer(strategy='constant', fill_value='missing') inside legacy Pipeline",
        },
        "feature_null_counts_after_project_preprocessing": null_counts,
    }


def build_predictions_frame(
    source_frame: pd.DataFrame,
    expected_price_proxy: np.ndarray,
    expected_currency: str,
) -> pd.DataFrame:
    result = source_frame.copy()
    result["listing_price"] = pd.to_numeric(result["listing_price"], errors="coerce")
    result["expected_price_proxy"] = expected_price_proxy
    result["expected_price_proxy_currency"] = expected_currency
    result["delta_abs"] = result["expected_price_proxy"] - result["listing_price"]
    result["delta_pct"] = result["delta_abs"] / result["listing_price"]
    result["delta_pct_percent"] = result["delta_pct"] * 100.0
    result = result.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["listing_price", "expected_price_proxy", "delta_abs", "delta_pct"]
    )

    if "listing_id" not in result.columns:
        result["listing_id"] = np.arange(1, len(result) + 1)
    if "area" not in result.columns and "total_area_m2" in result.columns:
        result["area"] = result["total_area_m2"]
    if "total_area_m2" not in result.columns and "area" in result.columns:
        result["total_area_m2"] = result["area"]
    if "floor" not in result.columns and "level" in result.columns:
        result["floor"] = result["level"]
    if "total_floors" not in result.columns and "levels" in result.columns:
        result["total_floors"] = result["levels"]

    output_columns = [
        "listing_id",
        "listing_price",
        "listing_currency",
        "expected_price_proxy",
        "expected_price_proxy_currency",
        "delta_abs",
        "delta_pct",
        "delta_pct_percent",
        "area",
        "total_area_m2",
        "rooms",
        "floor",
        "total_floors",
        "city",
        "district",
        "region",
        "building_type",
        "object_type",
    ]
    return result.loc[:, [column for column in output_columns if column in result.columns]]


def min_median_max(series: pd.Series | np.ndarray) -> dict[str, float]:
    values = pd.to_numeric(pd.Series(series), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "min": float(values.min()),
        "median": float(values.median()),
        "max": float(values.max()),
    }


def sanity_check(predictions: pd.DataFrame, raw_predictions: np.ndarray) -> dict[str, Any]:
    expected = pd.to_numeric(predictions["expected_price_proxy"], errors="coerce")
    delta_pct = pd.to_numeric(predictions["delta_pct"], errors="coerce")
    listing_price = pd.to_numeric(predictions["listing_price"], errors="coerce")
    rounded_unique_delta = int(delta_pct.round(8).nunique(dropna=True))
    zero_share = float((expected == 0).mean())
    checks = {
        "expected_price_proxy_nan_count": int(expected.isna().sum()),
        "expected_price_proxy_negative_count": int((expected < 0).sum()),
        "expected_price_proxy_zero_share": zero_share,
        "delta_pct_unique_rounded_8": rounded_unique_delta,
        "delta_pct_all_minus_one": bool((delta_pct == -1.0).all()),
        "listing_price_min_median_max": min_median_max(listing_price),
        "expected_price_proxy_min_median_max": min_median_max(expected),
        "raw_prediction_min_median_max": min_median_max(raw_predictions),
        "first_10_rows": predictions[
            ["listing_price", "expected_price_proxy", "delta_abs", "delta_pct"]
        ].head(10).to_dict(orient="records"),
    }
    checks["passed"] = (
        checks["expected_price_proxy_nan_count"] == 0
        and checks["expected_price_proxy_negative_count"] == 0
        and zero_share <= 0.5
        and rounded_unique_delta > 1
        and not checks["delta_pct_all_minus_one"]
    )
    if not checks["passed"]:
        reasons: list[str] = []
        if checks["expected_price_proxy_nan_count"]:
            reasons.append("expected_price_proxy contains NaN")
        if checks["expected_price_proxy_negative_count"]:
            reasons.append("expected_price_proxy contains negative values")
        if zero_share > 0.5:
            reasons.append("expected_price_proxy is zero for majority of objects")
        if rounded_unique_delta <= 1:
            reasons.append("delta_pct is constant")
        if checks["delta_pct_all_minus_one"]:
            reasons.append("delta_pct is -1.0 for all objects")
        checks["failure_reasons"] = reasons
    return checks


def compute_stats(delta_pct: pd.Series) -> dict[str, float | int]:
    values = pd.to_numeric(delta_pct, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        raise ValueError("No valid delta_pct values.")
    stats = {
        "count": int(values.count()),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std(ddof=1)),
        "min": float(values.min()),
        "max": float(values.max()),
        "q05": float(values.quantile(0.05)),
        "q25": float(values.quantile(0.25)),
        "q75": float(values.quantile(0.75)),
        "q95": float(values.quantile(0.95)),
        "share_delta_pct_gt_0": float((values > 0).mean()),
        "share_delta_pct_lt_0": float((values < 0).mean()),
        "share_abs_delta_pct_le_0_1": float((values.abs() <= 0.1).mean()),
        "share_delta_pct_ge_0_2": float((values >= 0.2).mean()),
        "share_delta_pct_le_minus_0_2": float((values <= -0.2).mean()),
    }
    stats["percent"] = {
        key: (value * 100.0 if key != "count" else value)
        for key, value in stats.items()
        if key
        in {
            "count",
            "mean",
            "median",
            "std",
            "min",
            "max",
            "q05",
            "q25",
            "q75",
            "q95",
        }
    }
    return stats


def save_histogram(predictions: pd.DataFrame, stats: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = predictions["delta_pct_percent"].to_numpy(dtype=float)
    p01, p99 = np.percentile(values, [1, 99])
    bins = np.linspace(p01, p99, 41) if p01 < p99 else 30

    figure, axis = plt.subplots(figsize=(11, 6.5), facecolor="white")
    axis.set_facecolor("white")
    axis.hist(values, bins=bins, color="0.25", edgecolor="black", linewidth=0.7, alpha=1.0)
    axis.axvline(
        float(stats["percent"]["mean"]),
        color="black",
        linestyle="--",
        linewidth=2,
        label=f"Среднее: {stats['percent']['mean']:.2f}%",
    )
    axis.axvline(
        float(stats["percent"]["median"]),
        color="black",
        linestyle="-.",
        linewidth=2,
        label=f"Медиана: {stats['percent']['median']:.2f}%",
    )
    axis.set_title("Распределение относительного отклонения delta_pct")
    axis.set_xlabel("Относительное отклонение delta_pct, %")
    axis.set_ylabel("Количество объектов")
    figure.text(0.5, 0.01, f"Гистограмма показана в диапазоне 1-99 перцентилей: {p01:.2f}% ... {p99:.2f}%; статистика рассчитана по всем объектам.", ha="center", fontsize=9)
    axis.legend(frameon=False)
    axis.grid(axis="y", color="0.85", alpha=1.0)
    for spine in axis.spines.values():
        spine.set_color("black")
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    plt.savefig(output_path, dpi=200)
    plt.close()


def _fmt(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}"


def _fmt_pct(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def build_summary(
    *,
    payload: dict[str, Any],
    source: SourceCandidate,
    source_audit: dict[str, Any],
    feature_audit: dict[str, Any],
    stats_payload: dict[str, Any],
    predictions_path: Path,
    stats_path: Path,
    histogram_path: Path,
) -> str:
    stats = stats_payload["stats"]
    percent = stats["percent"]
    table_rows = [
        ("count", stats["count"], percent["count"]),
        ("mean", stats["mean"], percent["mean"]),
        ("median", stats["median"], percent["median"]),
        ("std", stats["std"], percent["std"]),
        ("min", stats["min"], percent["min"]),
        ("max", stats["max"], percent["max"]),
        ("q05", stats["q05"], percent["q05"]),
        ("q25", stats["q25"], percent["q25"]),
        ("q75", stats["q75"], percent["q75"]),
        ("q95", stats["q95"], percent["q95"]),
        ("share_delta_pct_gt_0", stats["share_delta_pct_gt_0"], None),
        ("share_delta_pct_lt_0", stats["share_delta_pct_lt_0"], None),
        ("share_abs_delta_pct_le_0_1", stats["share_abs_delta_pct_le_0_1"], None),
        ("share_delta_pct_ge_0_2", stats["share_delta_pct_ge_0_2"], None),
        ("share_delta_pct_le_minus_0_2", stats["share_delta_pct_le_minus_0_2"], None),
    ]
    lines = [
        "# Распределение delta_pct для legacy-модели на 1000 объектах",
        "",
        "## Модель",
        "",
        f"- Artifact: `{DEFAULT_MODEL_PATH}`.",
        f"- Тип artifact: `{type(payload).__name__}`.",
        f"- Тип модели внутри: `{payload['model'].__class__.__module__}.{payload['model'].__class__.__name__}`.",
        f"- Target: `{payload.get('target_column') or payload['feature_config'].get('target_column')}`.",
        f"- Обратное преобразование: `{stats_payload['prediction']['inverse_transform']}`.",
        "",
        "## Источник данных",
        "",
        f"- Использован источник: `{source.description}`.",
        "- Старый `analytics/reports/control_sample_predictions.csv` не использовался как основной источник, потому что в нем только 32 строки и предыдущий расчет дал вырожденное распределение.",
        f"- Исходных строк: {stats_payload['rows']['source_rows']}.",
        f"- После фильтрации: {stats_payload['rows']['filtered_rows']}.",
        f"- В финальной выборке: {stats_payload['rows']['sample_rows']}.",
        f"- Валюта расчета: `{stats_payload['currency']['comparison_currency']}`.",
        f"- FX rate: `{stats_payload['currency']['fx_rate']}`.",
        "",
        "## Признаки",
        "",
        f"- Используемые признаки: `{', '.join(feature_audit['feature_columns'])}`.",
        f"- Найдены в данных: `{', '.join(feature_audit['features_found_in_source'])}`.",
        f"- Сгенерированы как derived: `{', '.join(feature_audit['derived_features_generated'])}`.",
        f"- Отсутствовали в source и заполнялись pipeline: `{', '.join(feature_audit['features_missing_in_source']) or 'нет'}`.",
        "",
        "## Статистика delta_pct",
        "",
        "| Показатель | Доля | Проценты |",
        "|---|---:|---:|",
    ]
    for name, value, pct_value in table_rows:
        lines.append(f"| `{name}` | {_fmt(value)} | {'' if pct_value is None else _fmt(pct_value)} |")

    lines.extend(
        [
            "",
            "## Файлы",
            "",
            f"- CSV: `{predictions_path}`.",
            f"- JSON: `{stats_path}`.",
            f"- PNG: `{histogram_path}`.",
            "",
            "## Интерпретация для статьи",
            "",
            (
                f"На случайной контрольной выборке из {stats['count']} объектов legacy-модель дала "
                f"среднее относительное отклонение {percent['mean']:.2f}% и медианное отклонение "
                f"{percent['median']:.2f}%."
            ),
            (
                f"Доля объектов с положительным `delta_pct` составила {_fmt_pct(stats['share_delta_pct_gt_0'])}, "
                f"с отрицательным - {_fmt_pct(stats['share_delta_pct_lt_0'])}."
            ),
            (
                f"В диапазоне |delta_pct| <= 10% находится {_fmt_pct(stats['share_abs_delta_pct_le_0_1'])} "
                f"объектов; доля сильной переоценки `delta_pct >= 20%` равна "
                f"{_fmt_pct(stats['share_delta_pct_ge_0_2'])}, а сильной недооценки `delta_pct <= -20%` - "
                f"{_fmt_pct(stats['share_delta_pct_le_minus_0_2'])}."
            ),
            (
                "Расчет выполнен в USD, поэтому валютная конвертация не применялась; это соответствует target "
                "`price_usd` legacy artifact и полю `price_usd` выбранного raw dataset."
            ),
            "",
            "## Аудит источников",
            "",
            "```json",
            json.dumps(_jsonable(source_audit), ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_candidate(
    candidate: SourceCandidate,
    payload: dict[str, Any],
    feature_config: FeatureConfig,
    *,
    sample_size: int,
    random_state: int,
) -> dict[str, Any]:
    normalized = normalize_source_frame(candidate, feature_config)
    filtered = filter_valid_frame(normalized)
    sampled = sample_valid_frame(filtered, sample_size, random_state)
    if sampled.empty:
        raise ValueError("No valid rows after filtering.")

    feature_frame = create_model_features(sampled, feature_config)
    raw_predictions, expected_model_currency, prediction_meta = predict_expected_price(payload, feature_frame)
    listing_currencies = sampled["listing_currency"].fillna(candidate.listing_currency).astype(str).str.upper()
    dominant_listing_currency = str(listing_currencies.mode().iloc[0]) if not listing_currencies.empty else candidate.listing_currency
    expected, comparison_currency, fx_rate, conversion = convert_expected_currency(
        expected_model_currency,
        model_currency=model_output_currency(payload),
        listing_currency=dominant_listing_currency,
    )
    # Negative prices are invalid in output; keep raw prediction diagnostics and clip only after inverse transform.
    expected = np.clip(expected, a_min=0.0, a_max=None)
    predictions = build_predictions_frame(sampled, expected, comparison_currency)
    checks = sanity_check(predictions, raw_predictions)
    feature_audit = build_feature_audit(sampled, feature_config, feature_frame)
    return {
        "source": candidate,
        "source_frame": normalized,
        "filtered_frame": filtered,
        "sampled_frame": sampled,
        "predictions": predictions,
        "raw_predictions": raw_predictions,
        "sanity": checks,
        "feature_audit": feature_audit,
        "prediction": {
            **prediction_meta,
            "model_output_currency": model_output_currency(payload),
            "comparison_currency": comparison_currency,
            "fx_rate": fx_rate,
            "currency_conversion": conversion,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_legacy_payload(args.model_path)
    feature_config = feature_config_from_payload(payload)
    candidates, source_audit = load_source_candidates(args.force_download)

    diagnostics: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    passed_fallback: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate.is_old_32_row_control_sample:
            diagnostics.append(
                {
                    "source": candidate.name,
                    "skipped": True,
                    "reason": "old 32-row report is diagnostic only",
                    "rows": int(len(candidate.frame)),
                }
            )
            continue
        try:
            result = evaluate_candidate(
                candidate,
                payload,
                feature_config,
                sample_size=args.sample_size,
                random_state=args.random_state,
            )
        except Exception as exc:
            diagnostics.append(
                {
                    "source": candidate.name,
                    "passed": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "rows": int(len(candidate.frame)),
                }
            )
            continue
        diagnostics.append(
            {
                "source": candidate.name,
                "priority": candidate.priority,
                "rows": int(len(candidate.frame)),
                "filtered_rows": int(len(result["filtered_frame"])),
                "sample_rows": int(len(result["predictions"])),
                "sanity": result["sanity"],
            }
        )
        if result["sanity"]["passed"]:
            if len(result["predictions"]) >= args.sample_size:
                selected = result
                break
            if passed_fallback is None:
                passed_fallback = result

    if selected is None:
        selected = passed_fallback

    if selected is None:
        diagnostic_payload = {
            "error": "No source produced a non-degenerate legacy delta_pct distribution.",
            "diagnostics": diagnostics,
            "source_audit": source_audit,
        }
        args.stats_path.parent.mkdir(parents=True, exist_ok=True)
        with args.stats_path.open("w", encoding="utf-8") as file:
            json.dump(_jsonable(diagnostic_payload), file, ensure_ascii=False, indent=2)
        raise RuntimeError(
            f"No valid non-degenerate distribution. Diagnostics saved to {args.stats_path}"
        )

    source = selected["source"]
    predictions = selected["predictions"]
    stats = compute_stats(predictions["delta_pct"])
    stats_payload = {
        "model": {
            "artifact_path": args.model_path,
            "artifact_type": type(payload).__name__,
            "model_name": payload.get("model_name"),
            "model_type": f"{payload['model'].__class__.__module__}.{payload['model'].__class__.__name__}",
            "target_column": payload.get("target_column") or payload["feature_config"].get("target_column"),
            "feature_config": payload["feature_config"],
        },
        "source": {
            "selected_source": source.name,
            "selected_priority": source.priority,
            "description": source.description,
            "old_control_sample_not_used_reason": (
                "analytics/reports/control_sample_predictions.csv contains only 32 rows and produced "
                "a degenerate delta_pct=-1.0 distribution in the previous calculation"
            ),
        },
        "rows": {
            "source_rows": int(len(source.frame)),
            "filtered_rows": int(len(selected["filtered_frame"])),
            "sample_rows": int(len(predictions)),
            "target_sample_size": int(args.sample_size),
            "random_state": int(args.random_state),
        },
        "currency": {
            "listing_currency": source.listing_currency,
            "model_output_currency": selected["prediction"]["model_output_currency"],
            "comparison_currency": selected["prediction"]["comparison_currency"],
            "fx_rate": selected["prediction"]["fx_rate"],
            "currency_conversion": selected["prediction"]["currency_conversion"],
        },
        "prediction": selected["prediction"],
        "feature_audit": selected["feature_audit"],
        "sanity_checks": selected["sanity"],
        "candidate_diagnostics": diagnostics,
        "source_audit": source_audit,
        "stats": stats,
    }

    args.predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.predictions_path, index=False)
    save_histogram(predictions, stats, args.histogram_path)
    with args.stats_path.open("w", encoding="utf-8") as file:
        json.dump(_jsonable(stats_payload), file, ensure_ascii=False, indent=2)
    summary = build_summary(
        payload=payload,
        source=source,
        source_audit=source_audit,
        feature_audit=selected["feature_audit"],
        stats_payload=stats_payload,
        predictions_path=args.predictions_path,
        stats_path=args.stats_path,
        histogram_path=args.histogram_path,
    )
    args.summary_path.write_text(summary, encoding="utf-8")
    return stats_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build legacy delta_pct distribution on a 1000-row sample.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--stats-path", type=Path, default=DEFAULT_STATS_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--histogram-path", type=Path, default=DEFAULT_HISTOGRAM_PATH)
    parser.add_argument("--sample-size", type=int, default=TARGET_SAMPLE_SIZE)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    stats = payload["stats"]
    print(f"Saved predictions: {args.predictions_path}")
    print(f"Saved stats: {args.stats_path}")
    print(f"Saved summary: {args.summary_path}")
    print(f"Saved histogram: {args.histogram_path}")
    print(
        "delta_pct stats: "
        f"count={stats['count']}, mean={stats['mean']:.10f}, median={stats['median']:.10f}, "
        f"std={stats['std']:.10f}, min={stats['min']:.10f}, max={stats['max']:.10f}, "
        f"q05={stats['q05']:.10f}, q25={stats['q25']:.10f}, "
        f"q75={stats['q75']:.10f}, q95={stats['q95']:.10f}"
    )


if __name__ == "__main__":
    main()
