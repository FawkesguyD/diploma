from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", "/tmp/real_estate_analytics_matplotlib")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.normalization import create_model_features
from model.ml.model.persistence import inverse_transform_predictions, resolve_target_transform


DEFAULT_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "linear_regression_baseline.joblib"
DEFAULT_CONTROL_SAMPLE_PATH = PROJECT_ROOT / "analytics" / "reports" / "control_sample_predictions.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analytics" / "reports"
DEFAULT_PREDICTIONS_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_predictions.csv"
DEFAULT_STATS_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_stats.json"
DEFAULT_SUMMARY_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_summary.md"
DEFAULT_HISTOGRAM_PATH = DEFAULT_REPORTS_DIR / "legacy_delta_pct_distribution.png"
DEFAULT_USD_TO_RUB_RATE = 90.0


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


def load_legacy_payload(model_path: Path) -> dict[str, Any]:
    payload = joblib.load(model_path)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected model bundle dict, got {type(payload).__name__}: {model_path}")
    if "model" not in payload or "feature_config" not in payload:
        raise KeyError("Legacy artifact must contain 'model' and 'feature_config'.")
    return payload


def feature_config_from_payload(payload: dict[str, Any]) -> FeatureConfig:
    return FeatureConfig(**payload["feature_config"])


def normalize_control_sample_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    aliases = {
        "area": "total_area_m2",
        "kitchen_area": "kitchen_area_m2",
        "level": "floor",
        "levels": "total_floors",
    }
    for source, target in aliases.items():
        if source in result.columns and target not in result.columns:
            result[target] = result[source]
    if "listing_currency" not in result.columns:
        result["listing_currency"] = "RUB"
    return result


def _valid_listing_price_mask(frame: pd.DataFrame) -> pd.Series:
    listing_price = pd.to_numeric(frame["listing_price"], errors="coerce")
    return listing_price.notna() & np.isfinite(listing_price) & (listing_price > 0)


def _model_output_currency(payload: dict[str, Any]) -> str:
    base_currency = payload.get("base_currency")
    if base_currency:
        return str(base_currency).upper()
    target_column = str(payload.get("target_column") or payload["feature_config"].get("target_column") or "")
    if target_column.endswith("_usd"):
        return "USD"
    if target_column in {"price", "listing_price"}:
        return "RUB"
    return "UNKNOWN"


def predict_expected_price_proxy(
    payload: dict[str, Any],
    frame: pd.DataFrame,
    *,
    usd_to_rub_rate: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    feature_config = feature_config_from_payload(payload)
    feature_frame = create_model_features(frame, feature_config)
    raw_predictions = payload["model"].predict(feature_frame)
    target_transform = resolve_target_transform(payload)
    predictions = inverse_transform_predictions(raw_predictions, target_transform)
    predictions = np.clip(np.asarray(predictions, dtype=float), a_min=0.0, a_max=None)

    model_currency = _model_output_currency(payload)
    listing_currencies = set(frame["listing_currency"].fillna("RUB").astype(str).str.upper().unique())
    converted_to_rub = model_currency == "USD" and listing_currencies <= {"RUB"}
    if converted_to_rub:
        predictions = predictions * usd_to_rub_rate
        output_currency = "RUB"
    else:
        output_currency = model_currency

    metadata = {
        "model_output_currency": model_currency,
        "expected_price_proxy_currency": output_currency,
        "usd_to_rub_rate": usd_to_rub_rate if converted_to_rub else None,
        "currency_conversion": "USD_to_RUB" if converted_to_rub else "none",
        "feature_columns": feature_config.feature_columns,
        "target_transform": target_transform,
    }
    return predictions, metadata


def build_prediction_frame(
    source_frame: pd.DataFrame,
    expected_price_proxy: np.ndarray,
) -> pd.DataFrame:
    result = source_frame.copy()
    result["listing_price"] = pd.to_numeric(result["listing_price"], errors="coerce")
    result["expected_price_proxy"] = expected_price_proxy
    result["delta_abs"] = result["expected_price_proxy"] - result["listing_price"]
    result["delta_pct"] = result["delta_abs"] / result["listing_price"]
    result = result.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["listing_price", "expected_price_proxy", "delta_abs", "delta_pct"]
    )

    if "listing_id" not in result.columns:
        result["listing_id"] = np.arange(1, len(result) + 1)
    if "total_area_m2" not in result.columns and "area" in result.columns:
        result["total_area_m2"] = result["area"]
    if "floor" not in result.columns and "level" in result.columns:
        result["floor"] = result["level"]
    if "total_floors" not in result.columns and "levels" in result.columns:
        result["total_floors"] = result["levels"]

    requested_columns = [
        "listing_id",
        "listing_price",
        "expected_price_proxy",
        "delta_abs",
        "delta_pct",
        "area",
        "total_area_m2",
        "rooms",
        "floor",
        "total_floors",
        "district",
        "city",
        "region",
        "building_type",
        "object_type",
    ]
    return result.loc[:, [column for column in requested_columns if column in result.columns]]


def compute_delta_stats(delta_pct: pd.Series) -> dict[str, float | int]:
    values = pd.to_numeric(delta_pct, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        raise ValueError("No valid delta_pct values to summarize.")
    return {
        "count": int(values.count()),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std(ddof=1)),
        "min": float(values.min()),
        "max": float(values.max()),
        "q25": float(values.quantile(0.25)),
        "q75": float(values.quantile(0.75)),
        "share_delta_pct_gt_0": float((values > 0).mean()),
        "share_delta_pct_lt_0": float((values < 0).mean()),
        "share_abs_delta_pct_le_0_1": float((values.abs() <= 0.1).mean()),
        "share_delta_pct_ge_0_2": float((values >= 0.2).mean()),
        "share_delta_pct_le_minus_0_2": float((values <= -0.2).mean()),
    }


def save_histogram(predictions: pd.DataFrame, stats: dict[str, float | int], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    delta_pct_percent = predictions["delta_pct"].to_numpy(dtype=float) * 100.0
    mean_percent = float(stats["mean"]) * 100.0
    median_percent = float(stats["median"]) * 100.0

    plt.figure(figsize=(10, 6))
    bins = min(30, max(8, int(np.sqrt(len(delta_pct_percent)))))
    plt.hist(delta_pct_percent, bins=bins, color="#4C78A8", edgecolor="white", alpha=0.9)
    plt.axvline(mean_percent, color="#F58518", linestyle="--", linewidth=2, label=f"Среднее: {mean_percent:.2f}%")
    plt.axvline(median_percent, color="#54A24B", linestyle="-.", linewidth=2, label=f"Медиана: {median_percent:.2f}%")
    plt.title("Распределение относительного отклонения delta_pct, legacy-модель")
    plt.xlabel("delta_pct, %")
    plt.ylabel("Количество объектов")
    plt.legend()
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def _format_number(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}"


def _format_pct(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def build_summary_markdown(
    *,
    model_path: Path,
    source_path: Path,
    histogram_path: Path,
    stats_path: Path,
    predictions_path: Path,
    stats: dict[str, float | int],
    audit: dict[str, Any],
) -> str:
    stats_rows = [
        ("count", stats["count"]),
        ("mean", stats["mean"]),
        ("median", stats["median"]),
        ("std", stats["std"]),
        ("min", stats["min"]),
        ("max", stats["max"]),
        ("q25", stats["q25"]),
        ("q75", stats["q75"]),
        ("share_delta_pct_gt_0", stats["share_delta_pct_gt_0"]),
        ("share_delta_pct_lt_0", stats["share_delta_pct_lt_0"]),
        ("share_abs_delta_pct_le_0_1", stats["share_abs_delta_pct_le_0_1"]),
        ("share_delta_pct_ge_0_2", stats["share_delta_pct_ge_0_2"]),
        ("share_delta_pct_le_minus_0_2", stats["share_delta_pct_le_minus_0_2"]),
    ]
    table_lines = ["| Показатель | Значение |", "|---|---:|"]
    table_lines.extend(f"| `{name}` | {_format_number(value)} |" for name, value in stats_rows)

    mean_pct = _format_pct(float(stats["mean"]))
    median_pct = _format_pct(float(stats["median"]))
    positive_pct = _format_pct(float(stats["share_delta_pct_gt_0"]))
    negative_pct = _format_pct(float(stats["share_delta_pct_lt_0"]))
    close_pct = _format_pct(float(stats["share_abs_delta_pct_le_0_1"]))
    ge_20_pct = _format_pct(float(stats["share_delta_pct_ge_0_2"]))
    le_minus_20_pct = _format_pct(float(stats["share_delta_pct_le_minus_0_2"]))

    return "\n".join(
        [
            "# Распределение delta_pct для legacy-модели",
            "",
            "## 1. Модель",
            "",
            f"- Использован artifact: `{model_path}`.",
            f"- Структура artifact: `{audit['artifact_type']}` bundle с моделью `{audit['model_type']}`.",
            f"- Target artifact: `{audit['target_column']}`, transform: `{audit['target_transform']}`.",
            f"- Подготовка признаков: `ml.model.normalization.create_model_features` по `feature_config` из artifact.",
            "",
            "## 2. Данные",
            "",
            f"- Источник: `{source_path}`.",
            "- Это сохраненная контрольная выборка из `analytics_control_objects`, использованная в статье для сравнения valuation-подходов.",
            f"- В расчет вошло объектов: {stats['count']}.",
            f"- Валюта `expected_price_proxy`: `{audit['prediction_metadata']['expected_price_proxy_currency']}`.",
            f"- Конвертация: `{audit['prediction_metadata']['currency_conversion']}`.",
            "",
            "## 3. Статистика delta_pct",
            "",
            *table_lines,
            "",
            "## 4. Файлы",
            "",
            f"- PNG-гистограмма: `{histogram_path}`.",
            f"- CSV с расчетами: `{predictions_path}`.",
            f"- JSON со статистикой: `{stats_path}`.",
            "",
            "## 5. Интерпретация для статьи",
            "",
            (
                f"На контрольной выборке из {stats['count']} объектов среднее относительное отклонение "
                f"legacy-модели составило {mean_pct}, медианное - {median_pct}."
            ),
            (
                f"Положительное отклонение наблюдается у {positive_pct} объектов, отрицательное - у {negative_pct}, "
                "что показывает направление смещения proxy-оценки относительно цены объявления."
            ),
            (
                f"В интервале |delta_pct| <= 10% находится {close_pct} объектов; доля объектов с "
                f"delta_pct >= 20% равна {ge_20_pct}, а с delta_pct <= -20% - {le_minus_20_pct}."
            ),
            (
                "Поскольку legacy artifact обучен на `price_usd`, а контрольная выборка хранит `listing_price` "
                "в RUB, прогноз перед расчетом delta_pct приведен к RUB фиксированным курсом 90 RUB/USD."
            ),
        ]
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    payload = load_legacy_payload(args.model_path)
    source_frame = pd.read_csv(args.control_sample_path)
    source_frame = normalize_control_sample_columns(source_frame)
    if "listing_price" not in source_frame.columns:
        raise KeyError("Control sample must contain listing_price.")

    valid_frame = source_frame.loc[_valid_listing_price_mask(source_frame)].reset_index(drop=True)
    expected_price_proxy, prediction_metadata = predict_expected_price_proxy(
        payload,
        valid_frame,
        usd_to_rub_rate=args.usd_to_rub_rate,
    )
    predictions = build_prediction_frame(valid_frame, expected_price_proxy)
    stats = compute_delta_stats(predictions["delta_pct"])

    args.reports_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.predictions_path, index=False)
    save_histogram(predictions, stats, args.histogram_path)

    audit = {
        "artifact_path": args.model_path,
        "artifact_exists": args.model_path.exists(),
        "artifact_type": type(payload).__name__,
        "model_name": payload.get("model_name"),
        "model_type": f"{payload['model'].__class__.__module__}.{payload['model'].__class__.__name__}",
        "target_column": payload.get("target_column") or payload["feature_config"].get("target_column"),
        "target_transform": prediction_metadata["target_transform"],
        "feature_preparation": "ml.model.normalization.create_model_features",
        "control_sample_source": args.control_sample_path,
        "rows_before_listing_price_filter": int(len(source_frame)),
        "rows_after_listing_price_filter": int(len(valid_frame)),
        "prediction_metadata": prediction_metadata,
    }
    stats_payload = {
        "audit": audit,
        "stats": stats,
    }
    with args.stats_path.open("w", encoding="utf-8") as file:
        json.dump(_jsonable(stats_payload), file, ensure_ascii=False, indent=2)

    summary = build_summary_markdown(
        model_path=args.model_path,
        source_path=args.control_sample_path,
        histogram_path=args.histogram_path,
        stats_path=args.stats_path,
        predictions_path=args.predictions_path,
        stats=stats,
        audit=audit,
    )
    args.summary_path.write_text(summary, encoding="utf-8")

    return {
        "stats": stats,
        "audit": audit,
        "predictions_path": args.predictions_path,
        "stats_path": args.stats_path,
        "summary_path": args.summary_path,
        "histogram_path": args.histogram_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build legacy delta_pct distribution report.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--control-sample-path", type=Path, default=DEFAULT_CONTROL_SAMPLE_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--stats-path", type=Path, default=DEFAULT_STATS_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--histogram-path", type=Path, default=DEFAULT_HISTOGRAM_PATH)
    parser.add_argument("--usd-to-rub-rate", type=float, default=DEFAULT_USD_TO_RUB_RATE)
    return parser.parse_args()


def main() -> None:
    result = run(parse_args())
    stats = result["stats"]
    print(f"Saved predictions: {result['predictions_path']}")
    print(f"Saved stats: {result['stats_path']}")
    print(f"Saved summary: {result['summary_path']}")
    print(f"Saved histogram: {result['histogram_path']}")
    print(
        "delta_pct stats: "
        f"count={stats['count']}, mean={stats['mean']:.6f}, median={stats['median']:.6f}, "
        f"std={stats['std']:.6f}, min={stats['min']:.6f}, max={stats['max']:.6f}, "
        f"q25={stats['q25']:.6f}, q75={stats['q75']:.6f}"
    )


if __name__ == "__main__":
    main()
