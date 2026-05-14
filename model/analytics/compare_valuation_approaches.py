from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", "/tmp/real_estate_analytics_matplotlib")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from model.analytics.charts.valuation_comparison import save_valuation_comparison_charts
from model.analytics.config import AnalyticsConfig
from model.analytics.control_sample import CONTROL_SAMPLE_TABLE
from model.analytics.valuation_approaches import (
    FORMULA_COEFFICIENTS,
    FORMULA_LIMITATION,
    PRICE_PER_METER_LIMITATION,
    build_comparison_frame,
    build_metrics_frame,
    build_my_model_metrics_frame,
    build_ranking_comparison_frame,
)
from model.ml.model.utils import ensure_directory, save_json
from model.shared.db.session import create_db_engine


PREDICTION_COLUMNS = [
    "source_object_id",
    "normalized_listing_id",
    "raw_listing_id",
    "listing_id",
    "listing_price",
    "listing_currency",
    "target_proxy_price",
    "target_proxy_basis",
    "area",
    "rooms",
    "kitchen_area",
    "level",
    "levels",
    "building_type",
    "object_type",
    "region",
    "latitude",
    "longitude",
    "price_per_meter_score",
    "price_per_meter_baseline_m2",
    "price_per_meter_segment",
    "price_per_meter_segment_rows",
    "price_per_meter_estimate",
    "price_per_meter_delta_abs",
    "price_per_meter_delta_pct",
    "price_per_meter_ranking_signal",
    "formula_estimate",
    "formula_delta_abs",
    "formula_delta_pct",
    "formula_ranking_signal",
    "regression_estimate",
    "regression_delta_abs",
    "regression_delta_pct",
    "regression_ranking_signal",
    "regression_error",
    "my_model_estimate",
    "my_model_delta_abs",
    "my_model_delta_pct",
    "my_model_ranking_signal",
    "my_model_error",
    "target_proxy_discount_signal",
    "target_proxy_opportunity_value",
]


def _parse_args() -> argparse.Namespace:
    defaults = AnalyticsConfig.from_env()
    parser = argparse.ArgumentParser(description="Сравнение valuation-подходов на control sample.")
    parser.add_argument("--output-dir", type=Path, default=defaults.reports_dir, help="Каталог отчетов.")
    parser.add_argument("--sample-seed", type=int, default=defaults.control_sample_seed, help="Seed контрольной выборки.")
    parser.add_argument("--limit", type=int, default=None, help="Опциональный лимит строк из контрольной таблицы.")
    return parser.parse_args()


def _config_from_args(args: argparse.Namespace) -> AnalyticsConfig:
    config = AnalyticsConfig.from_env()
    return AnalyticsConfig(
        database_url=config.database_url,
        output_dir=config.output_dir,
        reports_dir=args.output_dir,
        max_rows=config.max_rows,
        eval_max_rows=config.eval_max_rows,
        top_districts=config.top_districts,
        random_state=config.random_state,
        control_sample_size=config.control_sample_size,
        control_sample_seed=args.sample_seed,
        model_path=config.model_path,
        readiness_path=config.readiness_path,
        model_path_is_explicit=config.model_path_is_explicit,
        enable_reverse_geocoding=config.enable_reverse_geocoding,
        geocode_limit=config.geocode_limit,
    )


def load_control_objects(config: AnalyticsConfig, *, sample_seed: int, limit: int | None = None) -> pd.DataFrame:
    query = f"""
        select
          source_object_id,
          normalized_listing_id,
          raw_listing_id,
          listing_id,
          listing_price,
          listing_currency,
          target_proxy_price,
          target_source,
          area,
          rooms,
          kitchen_area,
          level,
          levels,
          building_type,
          object_type,
          region,
          latitude,
          longitude,
          source_url,
          sample_seed,
          sample_rank
        from {CONTROL_SAMPLE_TABLE}
        where sample_seed = :sample_seed
        order by sample_rank asc
    """
    if limit is not None:
        query += "\nlimit :limit"

    engine = create_db_engine(config.database_url)
    try:
        with engine.connect() as connection:
            return pd.read_sql_query(
                text(query),
                connection,
                params={"sample_seed": sample_seed, "limit": limit},
            )
    finally:
        engine.dispose()


def _existing_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _records_without_nan(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.replace({pd.NA: None}).to_json(orient="records", force_ascii=False))


def _format_metric(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    number = float(value)
    if abs(number) >= 1000:
        return f"{number:,.0f}".replace(",", " ")
    return f"{number:.4f}"


def write_summary_markdown(
    *,
    output_path: Path,
    comparison_frame: pd.DataFrame,
    metrics_frame: pd.DataFrame,
    generated_files: list[Path],
    regression_metadata: dict[str, Any],
) -> Path:
    value_metrics = metrics_frame[metrics_frame["metric_layer"] == "value"].copy()
    my_model_metrics = build_my_model_metrics_frame(metrics_frame)
    lines = [
        "# Сравнение valuation-подходов",
        "",
        "## Источник и выборка",
        "",
        f"- Строк в control sample: {len(comparison_frame)}.",
        "- Источник: `analytics_control_objects`, сформированная из `normalized_listings.normalized_payload`.",
        "- Target для метрик значения: `target_proxy_price`, то есть listing-based proxy target, а не цена сделки.",
        "- `my_model` использует активный runtime inference pipeline без переобучения.",
        f"- Источник моей модели: `{regression_metadata.get('model_source') or 'n/a'}`.",
        "",
        "## Метрики значения",
        "",
    ]
    for _, row in value_metrics.iterrows():
        lines.extend(
            [
                f"### {row['method']}",
                f"- rows: {_format_metric(row.get('rows'))}",
                f"- MAE: {_format_metric(row.get('mae'))}",
                f"- RMSE: {_format_metric(row.get('rmse'))}",
                f"- MAPE: {_format_metric(row.get('mape'))}",
                f"- R²: {_format_metric(row.get('r2'))}",
                "",
            ]
        )

    lines.extend(["## Показатели моей модели", ""])
    for _, row in my_model_metrics.iterrows():
        metric_name = row["metric"]
        lines.append(f"- {metric_name}: {_format_metric(row.get('value'))}")
    lines.append("")

    lines.extend(
        [
            "## Ranking-метрики",
            "",
            "- Spearman считается между ranking signal подхода и listing-based proxy discount signal.",
            "- NDCG@K, Precision@K и ProfitCapture@K используют только proxy signal на базе объявлений.",
            "",
            "## Ограничения",
            "",
            "- В control sample нет честного transaction truth; сравнение не доказывает реальную доходность сделки.",
            f"- {PRICE_PER_METER_LIMITATION}",
            f"- {FORMULA_LIMITATION}",
            "- My model estimate является model estimate, trained on listing data, и не должен называться точной рыночной ценой.",
            "",
            "## Сгенерированные файлы",
            "",
            *[f"- `{path.name}`" for path in generated_files],
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_outputs(
    *,
    output_dir: Path,
    comparison_frame: pd.DataFrame,
    metrics_frame: pd.DataFrame,
    ranking_frame: pd.DataFrame,
    regression_metadata: dict[str, Any],
) -> list[Path]:
    ensure_directory(output_dir)
    generated_files: list[Path] = []

    predictions_path = output_dir / "control_sample_predictions.csv"
    comparison_frame.loc[:, _existing_columns(comparison_frame, PREDICTION_COLUMNS)].to_csv(predictions_path, index=False)
    generated_files.append(predictions_path)

    metrics_path = output_dir / "control_sample_metrics.csv"
    metrics_frame.to_csv(metrics_path, index=False)
    generated_files.append(metrics_path)

    my_model_metrics_path = output_dir / "my_model_control_metrics.csv"
    my_model_metrics_frame = build_my_model_metrics_frame(metrics_frame)
    my_model_metrics_frame.to_csv(my_model_metrics_path, index=False)
    generated_files.append(my_model_metrics_path)

    ranking_path = output_dir / "ranking_comparison.csv"
    ranking_frame.to_csv(ranking_path, index=False)
    generated_files.append(ranking_path)

    generated_files.extend(save_valuation_comparison_charts(comparison_frame, metrics_frame, output_dir))

    summary_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(comparison_frame)),
        "source": CONTROL_SAMPLE_TABLE,
        "target_basis": "listing_price_proxy",
        "formula_coefficients": FORMULA_COEFFICIENTS,
        "limitations": [
            PRICE_PER_METER_LIMITATION,
            FORMULA_LIMITATION,
            "Control sample использует listing-based proxy target, а не transaction truth.",
        ],
        "regression_metadata": regression_metadata,
        "my_model_metrics": _records_without_nan(my_model_metrics_frame),
        "value_metrics": _records_without_nan(metrics_frame[metrics_frame["metric_layer"] == "value"]),
        "ranking_metrics": _records_without_nan(metrics_frame[metrics_frame["metric_layer"] == "ranking"]),
    }
    summary_json_path = output_dir / "summary.json"
    save_json(summary_payload, summary_json_path)
    generated_files.append(summary_json_path)

    summary_md_path = write_summary_markdown(
        output_path=output_dir / "summary.md",
        comparison_frame=comparison_frame,
        metrics_frame=metrics_frame,
        generated_files=generated_files,
        regression_metadata=regression_metadata,
    )
    generated_files.append(summary_md_path)
    return generated_files


def main() -> int:
    args = _parse_args()
    config = _config_from_args(args)
    control_frame = load_control_objects(config, sample_seed=args.sample_seed, limit=args.limit)
    if control_frame.empty:
        raise RuntimeError(
            "Контрольная таблица пуста. Сначала выполните: "
            "python analytics/bootstrap_control_sample.py"
        )

    comparison_frame, regression_metadata = build_comparison_frame(control_frame, config)
    metrics_frame = build_metrics_frame(comparison_frame)
    ranking_frame = build_ranking_comparison_frame(comparison_frame)
    generated_files = write_outputs(
        output_dir=config.reports_dir,
        comparison_frame=comparison_frame,
        metrics_frame=metrics_frame,
        ranking_frame=ranking_frame,
        regression_metadata=regression_metadata,
    )
    print(
        json.dumps(
            {"output_dir": str(config.reports_dir), "files": [str(path) for path in generated_files]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SQLAlchemyError as exc:
        print(
            "Ошибка подключения к БД при сравнении valuation-подходов. "
            f"Проверьте DATABASE_URL и таблицу {CONTROL_SAMPLE_TABLE}. Детали: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
