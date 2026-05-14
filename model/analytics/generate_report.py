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
from sqlalchemy.exc import SQLAlchemyError

from model.analytics.charts.dataset import save_dataset_charts
from model.analytics.charts.districts import save_top_districts_chart
from model.analytics.charts.model_quality import save_model_quality_charts, score_model_quality
from model.analytics.charts.prices import price_distribution_stats, save_price_charts
from model.analytics.config import AnalyticsConfig
from model.analytics.data_access.db import NORMALIZED_SOURCE_DESCRIPTION, load_normalized_dataset
from model.analytics.data_access.geocoding import enrich_missing_districts
from model.ml.model.utils import ensure_directory, save_json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Генерация аналитического отчета по нормализованным данным.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Каталог для результатов.")
    parser.add_argument("--max-rows", type=int, default=None, help="Лимит строк для EDA.")
    parser.add_argument("--eval-max-rows", type=int, default=None, help="Лимит строк для оценки модели.")
    parser.add_argument("--top-districts", type=int, default=None, help="Количество районов на графике.")
    parser.add_argument("--skip-model-quality", action="store_true", help="Не считать inference-графики качества.")
    parser.add_argument(
        "--enable-reverse-geocoding",
        action="store_true",
        help="Опционально обогатить пустые районы через существующий геосервис.",
    )
    return parser.parse_args()


def _config_from_args(args: argparse.Namespace) -> AnalyticsConfig:
    config = AnalyticsConfig.from_env()
    return AnalyticsConfig(
        database_url=config.database_url,
        output_dir=args.output_dir or config.output_dir,
        max_rows=args.max_rows if args.max_rows is not None else config.max_rows,
        eval_max_rows=args.eval_max_rows if args.eval_max_rows is not None else config.eval_max_rows,
        top_districts=args.top_districts if args.top_districts is not None else config.top_districts,
        random_state=config.random_state,
        model_path=config.model_path,
        readiness_path=config.readiness_path,
        model_path_is_explicit=config.model_path_is_explicit,
        enable_reverse_geocoding=args.enable_reverse_geocoding or config.enable_reverse_geocoding,
        geocode_limit=config.geocode_limit,
    )


def _value_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame[column].fillna("null").astype(str).value_counts().head(30).items()
    }


def build_dataset_profile(frame: pd.DataFrame) -> dict[str, Any]:
    non_null = {column: int(frame[column].notna().sum()) for column in frame.columns}
    numeric_columns = [
        "area",
        "kitchen_area",
        "rooms",
        "level",
        "levels",
        "year_built",
        "price",
        "price_per_m2",
    ]
    numeric_summary = {}
    for column in numeric_columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        numeric_summary[column] = {
            "count": int(len(values)),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "min": float(values.min()),
            "max": float(values.max()),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": NORMALIZED_SOURCE_DESCRIPTION,
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "non_null": non_null,
        "numeric_summary": numeric_summary,
        "validation_status_counts": _value_counts(frame, "validation_status"),
        "train_eligible_rows": int(frame["is_train_eligible"].sum()) if "is_train_eligible" in frame else 0,
        "top_district_groups": _value_counts(frame, "district_group"),
        "top_regions": _value_counts(frame, "region"),
    }


def _format_metric(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.0f}".replace(",", " ")
    return f"{number:.{digits}f}"


def write_summary(
    *,
    output_path: Path,
    config: AnalyticsConfig,
    profile: dict[str, Any],
    price_stats: dict[str, Any],
    generated_files: list[Path],
    quality_result: dict[str, Any] | None,
) -> Path:
    lines = [
        "# Аналитический отчет",
        "",
        "## Источник данных",
        "",
        f"- Источник истины: `{NORMALIZED_SOURCE_DESCRIPTION}`.",
        "- Данные читаются из БД через `shared.db.session` и ORM-модели `NormalizedListing`, `Listing`, `Valuation`.",
        "- Сырой CSV в аналитическом контуре не используется.",
        "",
        "## Профиль датасета",
        "",
        f"- Строк в выгрузке: {profile['rows']}.",
        f"- Train-eligible строк: {profile['train_eligible_rows']}.",
        f"- Лимит EDA: {config.max_rows}.",
        f"- Топ районов на графике: {config.top_districts}.",
        "",
        "## Цены",
        "",
        f"- Строк с положительной ценой: {price_stats.get('count', 0)}.",
        f"- Средняя цена: {_format_metric(price_stats.get('price_mean'))} RUB.",
        f"- Медианная цена: {_format_metric(price_stats.get('price_median'))} RUB.",
        f"- Асимметрия исходной цены: {_format_metric(price_stats.get('price_skew'))}.",
        f"- Асимметрия log(price): {_format_metric(price_stats.get('log_price_skew'))}.",
        "",
    ]

    if quality_result is not None:
        metrics = quality_result.get("metrics") or {}
        lines.extend(
            [
                "## Качество модели",
                "",
                f"- Источник модели: `{quality_result.get('model_source', 'n/a')}`.",
                f"- Оценено строк: {_format_metric(metrics.get('rows_evaluated'), 0)}.",
                f"- Пропущено inference validation: {_format_metric(metrics.get('rows_skipped'), 0)}.",
                f"- MAE: {_format_metric(metrics.get('mae'))} RUB.",
                f"- RMSE: {_format_metric(metrics.get('rmse'))} RUB.",
                f"- MAPE: {_format_metric(metrics.get('mape'))}.",
                f"- R²: {_format_metric(metrics.get('r2'))}.",
                "",
            ]
        )
        if quality_result.get("warning"):
            lines.extend(["### Ограничение", "", f"- {quality_result['warning']}", ""])
        bundle_metrics = quality_result.get("bundle_metrics") or {}
        if bundle_metrics:
            lines.extend(["### Метрики из артефакта модели", ""])
            for key, value in bundle_metrics.items():
                lines.append(f"- {key}: {_format_metric(value)}")
            lines.append("")

    lines.extend(
        [
            "## Сгенерированные файлы",
            "",
            *[f"- `{path.name}`" for path in generated_files],
            "",
            "## Ограничения",
            "",
            "- Если в `normalized_listings` нет явной валидационной или тестовой выборки, графики качества считаются на текущих нормализованных строках БД с целевой ценой.",
            "- Обратное геокодирование выключено по умолчанию, чтобы не создавать сетевые вызовы и нагрузку на провайдера.",
            "- Для районов используется `district`; если он пустой, резервная группа строится по `region`.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def main() -> int:
    args = _parse_args()
    config = _config_from_args(args)
    ensure_directory(config.output_dir)

    frame = load_normalized_dataset(config)
    if frame.empty:
        raise RuntimeError("В normalized_listings не найдено accepted-строк для аналитики.")
    frame = enrich_missing_districts(frame, config)

    generated_files: list[Path] = []
    generated_files.extend(save_dataset_charts(frame, config.output_dir, top_n=15))
    generated_files.extend(save_price_charts(frame, config.output_dir))
    generated_files.append(save_top_districts_chart(frame, config.output_dir, top_n=config.top_districts))

    profile = build_dataset_profile(frame)
    price_stats = price_distribution_stats(frame)
    save_json(profile, config.output_dir / "dataset_profile.json")
    generated_files.append(config.output_dir / "dataset_profile.json")

    quality_result: dict[str, Any] | None = None
    if not args.skip_model_quality:
        quality_result = score_model_quality(frame, config)
        predictions = quality_result.pop("predictions")
        generated_files.extend(save_model_quality_charts(predictions, config.output_dir))
        metrics_payload = {
            key: value
            for key, value in quality_result.items()
            if key not in {"first_errors"}
        }
        metrics_payload["first_errors"] = quality_result.get("first_errors", [])
        save_json(metrics_payload, config.output_dir / "metrics.json")
        generated_files.append(config.output_dir / "metrics.json")

    summary_path = write_summary(
        output_path=config.output_dir / "summary.md",
        config=config,
        profile=profile,
        price_stats=price_stats,
        generated_files=generated_files,
        quality_result=quality_result,
    )
    generated_files.append(summary_path)

    print(json.dumps({"output_dir": str(config.output_dir), "files": [str(path) for path in generated_files]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SQLAlchemyError as exc:
        print(
            "Ошибка подключения к БД аналитики. Проверьте DATABASE_URL и доступность PostgreSQL. "
            f"Детали: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
