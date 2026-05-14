from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory, to_serializable
from model.scripts.evaluate_limitations_impact import (
    fmt_float,
    fmt_int,
    fmt_mape,
    fmt_r2,
    format_parameter_value,
    markdown_impact_table,
    run_limitations_impact,
)


DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_MODEL_SUMMARY_PATH = DEFAULT_REPORTS_DIR / "legacy_model_summary.json"
DEFAULT_VALIDATION_METRICS_PATH = DEFAULT_REPORTS_DIR / "legacy_validation_metrics.json"
DEFAULT_FEATURE_ABLATION_PATH = DEFAULT_REPORTS_DIR / "legacy_feature_ablation_results.csv"
DEFAULT_HYPERPARAMETER_PATH = DEFAULT_REPORTS_DIR / "legacy_hyperparameter_sensitivity_results.csv"
DEFAULT_IMPACT_PATH = DEFAULT_REPORTS_DIR / "legacy_limitations_impact_matrix.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_REPORTS_DIR / "legacy_limitations_sensitivity_summary.json"
DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "ARTICLE_LEGACY_LIMITATIONS_SENSITIVITY.md"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_impact_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        if item["Ограничение"].startswith("Отсутствие признаков о ремонте"):
            item["Ограничение"] = (
                "Отсутствие признаков о ремонте, юридическом статусе и инфраструктуре"
            )
        normalized.append(item)
    return normalized


def markdown_feature_table(feature_rows: pd.DataFrame) -> str:
    lines = [
        "| Удаленный признак/группа | MAPE | ΔMAPE, п.п. | R² | ΔR² |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in feature_rows.iterrows():
        lines.append(
            f"| {row['Удаленный признак/группа']} | {fmt_mape(row['MAPE'])} | "
            f"{fmt_float(row['ΔMAPE, п.п.'], 2)} | {fmt_r2(row['R²'])} | {fmt_r2(row['ΔR²'])} |"
        )
    return "\n".join(lines)


def markdown_hyper_table(hyper_rows: pd.DataFrame) -> str:
    lines = [
        "| Параметр | Значение | MAPE | ΔMAPE, п.п. | R² | ΔR² |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in hyper_rows.iterrows():
        lines.append(
            f"| {row['Параметр']} | {format_parameter_value(row['Значение'])} | "
            f"{fmt_mape(row['MAPE'])} | {fmt_float(row['ΔMAPE, п.п.'], 2)} | "
            f"{fmt_r2(row['R²'])} | {fmt_r2(row['ΔR²'])} |"
        )
    return "\n".join(lines)


def markdown_metrics_table(metrics: dict[str, float]) -> str:
    return "\n".join(
        [
            "| Метрика | Значение |",
            "|---|---:|",
            f"| MAE | {fmt_int(metrics['MAE'])} USD |",
            f"| RMSE | {fmt_int(metrics['RMSE'])} USD |",
            f"| MAPE | {fmt_mape(metrics['MAPE'])} |",
            f"| R² | {fmt_r2(metrics['R²'])} |",
        ]
    )


def feature_sentences(ablation: pd.DataFrame) -> str:
    candidates = ablation[ablation["Удаленный признак/группа"] != "baseline"].copy()
    worsened = candidates[candidates["ΔMAPE, п.п."] > 0].sort_values(
        "ΔMAPE, п.п.",
        ascending=False,
    )
    weak = candidates.reindex(candidates["ΔMAPE, п.п."].abs().sort_values().index).head(3)

    if worsened.empty:
        first = "В ablation-анализе не было удаления признаков, которое ухудшило MAPE относительно baseline."
    else:
        labels = [
            f"{row['Удаленный признак/группа']} (+{fmt_float(row['ΔMAPE, п.п.'], 2)} п.п.)"
            for _, row in worsened.head(3).iterrows()
        ]
        first = "Наибольшее ухудшение MAPE дали: " + "; ".join(labels) + "."

    weak_labels = [
        f"{row['Удаленный признак/группа']} ({fmt_float(row['ΔMAPE, п.п.'], 2)} п.п.)"
        for _, row in weak.iterrows()
    ]
    second = "Слабее всего MAPE менялся для: " + "; ".join(weak_labels) + "."
    third = (
        "Это означает, что часть признаков в текущей схеме либо имеет небольшой вклад, "
        "либо частично дублируется другими признаками."
    )
    return f"{first} {second} {third}"


def hyper_sentences(hyper: pd.DataFrame) -> str:
    non_baseline = hyper[hyper["ΔMAPE, п.п."].abs() > 1e-12].copy()
    if non_baseline.empty:
        return "В проверенной сетке изменение параметров не изменило MAPE относительно baseline."

    strongest = non_baseline.assign(abs_delta=non_baseline["ΔMAPE, п.п."].abs()).sort_values(
        "abs_delta",
        ascending=False,
    ).iloc[0]
    text = (
        f"Наиболее заметное изменение MAPE получено для `{strongest['Параметр']}="
        f"{format_parameter_value(strongest['Значение'])}`: ΔMAPE "
        f"{fmt_float(strongest['ΔMAPE, п.п.'], 2)} п.п., ΔR² {fmt_r2(strongest['ΔR²'])}."
    )
    improved_complexity = hyper[
        ((hyper["Параметр"] == "depth") & (hyper["Значение"].astype(float) > 8))
        | ((hyper["Параметр"] == "iterations") & (hyper["Значение"].astype(float) > 800))
    ]
    if not improved_complexity.empty and (
        (improved_complexity["ΔMAPE, п.п."] < 0).any()
        or (improved_complexity["ΔR²"] > 0).any()
    ):
        text += (
            " Увеличение сложности в части конфигураций улучшало метрики, но это не является "
            "основанием для замены artifact без отдельной проверки на полной процедуре обучения."
        )
    else:
        text += " В проверенной сетке небольшие изменения параметров не дали резкого ухудшения качества."
    return text


def build_article(
    model_summary: dict[str, Any],
    validation_payload: dict[str, Any],
    impact_rows: list[dict[str, str]],
    ablation: pd.DataFrame,
    hyper: pd.DataFrame,
    summary: dict[str, Any],
) -> str:
    metrics = validation_payload["metrics"]
    feature_top = (
        ablation[ablation["Удаленный признак/группа"] != "baseline"]
        .sort_values("ΔMAPE, п.п.", ascending=False)
        .head(10)
    )
    feature_text = feature_sentences(ablation)
    hyper_text = hyper_sentences(hyper)
    impact_table = markdown_impact_table(impact_rows)
    split_text = (
        "фиксированном train/test split с test_size=0,2 и random_state=42"
        if summary["metadata"]["split_strategy"] == "fixed_train_test_split"
        else "5-fold cross-validation с random_state=42"
    )

    numerical_features = ", ".join(f"`{feature}`" for feature in model_summary["numerical_features"])
    categorical_features = ", ".join(f"`{feature}`" for feature in model_summary["categorical_features"])
    target_transform = model_summary.get("target_transform") or "log1p"
    inverse_transform = model_summary.get("inverse_transform") or "expm1"

    return f"""# Ограничения легаси-модели и анализ чувствительности

## 1. Проверка модели

- Путь к модели: `{model_summary['artifact_path']}`.
- Тип модели: `{model_summary['model_type']}`.
- Имя модели: `{model_summary['model_name']}`.
- Target: `{model_summary['target_column']}`.
- Валюта target: `{model_summary['target_currency']}`.
- Log transform: `{target_transform}`, обратное преобразование: `{inverse_transform}`.
- Количество признаков: {model_summary['total_feature_count']}, из них {len(model_summary['numerical_features'])} числовых и {len(model_summary['categorical_features'])} категориальных.
- Числовые признаки: {numerical_features}.
- Категориальные признаки: {categorical_features}.

## 2. Базовые метрики

{markdown_metrics_table(metrics)}

Примечание: target задан в USD. Для статьи дополнительно можно использовать пересчет по фиксированному курсу 1 USD = 90 RUB: MAE {fmt_int(metrics['MAE_RUB_at_90'])} RUB, RMSE {fmt_int(metrics['RMSE_RUB_at_90'])} RUB.

## 3. Таблица 5 - Матрица влияния ограничений на точность

{impact_table}

## 4. Анализ чувствительности к признакам

{markdown_feature_table(feature_top)}

{feature_text}

## 5. Анализ чувствительности к параметрам модели

{markdown_hyper_table(hyper)}

{hyper_text} Риск переобучения при увеличении сложности модели нельзя оценивать только по этой таблице, потому что эксперимент проверяет чувствительность на одной воспроизводимой схеме проверки.

## 6. Готовый фрагмент для статьи

Легаси-модель использовалась как proxy-valuation модель, так как обучение выполнялось на ценах объявлений, а не на данных фактических сделок. Для оценки ограничений были использованы доступные признаки, проверка качества на подгруппах и эксперименты чувствительности на {split_text}.

Таблица 5 - Матрица влияния ограничений на точность

{impact_table}

Часть ограничений не была рассчитана количественно, потому что в датасете нет данных фактических сделок и нет структурированных признаков юридического статуса и инфраструктуры. Поэтому полученные значения показывают чувствительность модели на данных объявлений, а не ошибку относительно независимой рыночной оценки.

Анализ чувствительности к признакам показал, что наибольшее ухудшение качества связано с группами и признаками, которые дают максимальный рост MAPE при удалении. {feature_text}

Анализ чувствительности к параметрам CatBoost показал, что модель заметнее всего реагировала на отдельные изменения параметров из проверенной сетки. {hyper_text}
"""


def save_outputs(
    impact_rows: list[dict[str, str]],
    summary: dict[str, Any],
    article: str,
    impact_path: Path,
    summary_path: Path,
    article_path: Path,
) -> None:
    ensure_directory(impact_path.parent)
    pd.DataFrame(impact_rows).to_csv(impact_path, index=False)
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(to_serializable(summary), file, ensure_ascii=False, indent=2)
    article_path.write_text(article, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legacy limitations matrix and article generator.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--model-summary-path", type=Path, default=DEFAULT_MODEL_SUMMARY_PATH)
    parser.add_argument("--validation-metrics-path", type=Path, default=DEFAULT_VALIDATION_METRICS_PATH)
    parser.add_argument("--feature-ablation-path", type=Path, default=DEFAULT_FEATURE_ABLATION_PATH)
    parser.add_argument("--hyperparameter-path", type=Path, default=DEFAULT_HYPERPARAMETER_PATH)
    parser.add_argument("--impact-path", type=Path, default=DEFAULT_IMPACT_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--article-path", type=Path, default=DEFAULT_ARTICLE_PATH)
    parser.add_argument("--strategy", choices=["cv", "holdout"], default="holdout")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--min-group-count", type=int, default=50)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    impact_rows, summary, _ = run_limitations_impact(
        data_path=args.data_path,
        feature_ablation_path=args.feature_ablation_path,
        hyperparameter_path=args.hyperparameter_path,
        n_splits=args.n_splits,
        strategy=args.strategy,
        test_size=args.test_size,
        random_state=args.random_state,
        min_group_count=args.min_group_count,
        force_download=args.force_download,
    )
    impact_rows = normalize_impact_rows(impact_rows)
    model_summary = read_json(args.model_summary_path)
    validation_payload = read_json(args.validation_metrics_path)
    ablation = pd.read_csv(args.feature_ablation_path)
    hyper = pd.read_csv(args.hyperparameter_path)
    summary["model_summary"] = model_summary
    summary["validation_metrics"] = validation_payload
    summary["impact_rows"] = impact_rows
    article = build_article(
        model_summary=model_summary,
        validation_payload=validation_payload,
        impact_rows=impact_rows,
        ablation=ablation,
        hyper=hyper,
        summary=summary,
    )
    save_outputs(
        impact_rows=impact_rows,
        summary=summary,
        article=article,
        impact_path=args.impact_path,
        summary_path=args.summary_path,
        article_path=args.article_path,
    )
    print(f"Saved legacy impact matrix: {args.impact_path}")
    print(f"Saved legacy summary: {args.summary_path}")
    print(f"Saved legacy article: {args.article_path}")


if __name__ == "__main__":
    main()
