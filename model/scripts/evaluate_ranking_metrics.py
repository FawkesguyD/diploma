from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_PATH = PROJECT_ROOT / "analytics" / "reports" / "control_sample_metrics.csv"
DEFAULT_PREDICTIONS_PATH = PROJECT_ROOT / "analytics" / "reports" / "control_sample_predictions.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports"
DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "ARTICLE_RANKING_METRICS.md"

METHOD_LABELS = {
    "price_per_meter": "Статистический метод",
    "formula": "Эвристический скоринг",
    "regression": "Регрессионная модель",
    "my_model": "CatBoost",
}
METHOD_SOURCE_NOTES = {
    "price_per_meter": "Existing analytics baseline: median price per m² segment.",
    "formula": "Existing analytics heuristic baseline with coefficients from apps.analytics_service.config.",
    "regression": (
        "Existing analytics row `regression` is produced by the active runtime inference bundle "
        "from the readiness manifest. In the current report it is not an independent "
        "`ml/artifacts/linear_regression_baseline.joblib` evaluation."
    ),
    "my_model": "Existing analytics alias for the active project model, currently CatBoost.",
}

METRIC_SPECS = [
    ("ndcg", 10.0, "NDCG@10"),
    ("ndcg", 20.0, "NDCG@20"),
    ("precision", 10.0, "Precision@10"),
    ("profit_capture", 10.0, "ProfitCapture@10"),
]

RANKING_NOTE = (
    "Ranking-метрики являются proxy-метриками: в control sample нет transaction truth, "
    "target_proxy_price совпадает с listing_price, а relevance построена по "
    "target_proxy_discount_signal на базе медианной цены за квадратный метр."
)

TTEST_NOTE = (
    "Статистическая значимость различий не рассчитывалась, так как в текущих отчетах "
    "сохранены только агрегированные значения метрик. Для t-test необходимо сохранить "
    "значения метрик по фолдам, bootstrap-выборкам или повторным запускам."
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    return pd.read_csv(path)


def _metric_value(
    metrics: pd.DataFrame,
    *,
    method: str,
    metric_layer: str,
    metric: str | None = None,
    k: float | None = None,
    value_column: str = "value",
) -> float | None:
    subset = metrics[(metrics["method"] == method) & (metrics["metric_layer"] == metric_layer)]
    if metric is not None:
        subset = subset[subset["metric"] == metric]
    if k is not None:
        subset = subset[subset["k"] == k]
    if subset.empty:
        return None
    value = subset.iloc[0].get(value_column)
    if pd.isna(value):
        return None
    return float(value)


def build_comparison_frame(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for method, label in METHOD_LABELS.items():
        row: dict[str, Any] = {"method": label, "method_id": method}
        for metric_name, k_value, output_name in METRIC_SPECS:
            row[output_name] = _metric_value(
                metrics,
                method=method,
                metric_layer="ranking",
                metric=metric_name,
                k=k_value,
            )

        value_rows = metrics[(metrics["method"] == method) & (metrics["metric_layer"] == "value")]
        if value_rows.empty:
            row["MAE"] = None
            row["MAPE"] = None
            row["rows"] = None
        else:
            value_row = value_rows.iloc[0]
            row["MAE"] = None if pd.isna(value_row.get("mae")) else float(value_row.get("mae"))
            row["MAPE"] = None if pd.isna(value_row.get("mape")) else float(value_row.get("mape"))
            row["rows"] = None if pd.isna(value_row.get("rows")) else int(value_row.get("rows"))
        row["source_note"] = METHOD_SOURCE_NOTES[method]
        rows.append(row)
    return pd.DataFrame(rows)


def inspect_relevance_source(predictions: pd.DataFrame) -> dict[str, Any]:
    required = {"target_proxy_price", "listing_price", "target_proxy_basis", "target_proxy_discount_signal"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        return {
            "available": False,
            "missing_columns": missing,
            "note": "Невозможно проверить источник relevance из-за отсутствующих колонок.",
        }

    target = pd.to_numeric(predictions["target_proxy_price"], errors="coerce")
    listing = pd.to_numeric(predictions["listing_price"], errors="coerce")
    equal_mask = np.isclose(target, listing, rtol=0.0, atol=1e-9, equal_nan=False)
    return {
        "available": True,
        "rows": int(len(predictions)),
        "target_proxy_basis": sorted(str(value) for value in predictions["target_proxy_basis"].dropna().unique()),
        "target_proxy_price_equals_listing_price": bool(equal_mask.all()),
        "positive_proxy_relevance_rows": int(
            (pd.to_numeric(predictions["target_proxy_discount_signal"], errors="coerce") > 0).sum()
        ),
        "note": RANKING_NOTE,
    }


def _format_metric(value: float | None, digits: int = 3) -> str:
    if value is None or not np.isfinite(value):
        return "не рассчитано"
    return f"{value:.{digits}f}".replace(".", ",")


def _format_percent(value: float | None, digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        return "не рассчитано"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _format_money(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "не рассчитано"
    return f"{int(round(value)):,} RUB".replace(",", " ")


def _best_method(frame: pd.DataFrame, metric: str) -> tuple[str, float] | None:
    values = frame[["method", "method_id", metric]].dropna()
    if values.empty:
        return None
    row = values.sort_values(metric, ascending=False).iloc[0]
    return str(row["method"]), float(row[metric])


def _catboost_advantage_text(frame: pd.DataFrame, metric: str, display_name: str, percent_points: bool) -> str:
    catboost_row = frame[frame["method_id"] == "my_model"]
    if catboost_row.empty or pd.isna(catboost_row.iloc[0].get(metric)):
        return f"По метрике {display_name} значение CatBoost не рассчитано."

    catboost_value = float(catboost_row.iloc[0][metric])
    baseline_values = frame[frame["method_id"] != "my_model"][["method", metric]].dropna()
    if baseline_values.empty:
        return f"По метрике {display_name} отсутствуют рассчитанные baseline-значения для сравнения."

    best_baseline = baseline_values.sort_values(metric, ascending=False).iloc[0]
    best_name = str(best_baseline["method"])
    best_value = float(best_baseline[metric])
    adv_abs = catboost_value - best_value
    adv_rel = None if best_value == 0 else adv_abs / best_value * 100
    direction = "выше" if adv_abs > 0 else "ниже" if adv_abs < 0 else "на уровне"
    unit = "процентного пункта" if percent_points else "пункта"
    abs_value = abs(adv_abs * 100) if percent_points else abs(adv_abs)
    abs_text = f"{abs_value:.2f}".replace(".", ",")
    rel_text = "не определено" if adv_rel is None else f"{adv_rel:.2f}%".replace(".", ",")
    value_text = _format_percent(catboost_value) if percent_points else _format_metric(catboost_value)

    if adv_abs == 0:
        return (
            f"По метрике {display_name} модель CatBoost получила значение {value_text}, "
            f"что совпадает с лучшим базовым методом ({best_name})."
        )
    return (
        f"По метрике {display_name} модель CatBoost получила значение {value_text}. "
        f"Это на {abs_text} {unit} {direction} лучшего базового метода ({best_name}); "
        f"относительное отличие составляет {rel_text}."
    )


def build_article_markdown(frame: pd.DataFrame, relevance_info: dict[str, Any]) -> str:
    lines = [
        "# Таблица 4 - Детальное сравнение методов",
        "",
        "Значения сформированы из `analytics/reports/control_sample_metrics.csv`. "
        "MAE рассчитан в RUB. MAPE и Precision@10 показаны в процентах.",
        "",
        f"Ограничение: {RANKING_NOTE}",
        "",
        "Отдельное ограничение по строке `Регрессионная модель`: в текущем "
        "`analytics/reports/control_sample_metrics.csv` эта строка соответствует `regression`, "
        "который был рассчитан через active runtime bundle из readiness manifest. "
        "Это не независимый расчет `ml/artifacts/linear_regression_baseline.joblib`; "
        "ranking-метрики для legacy linear regression artifact на той же контрольной выборке "
        "в проекте не сохранены.",
        "",
        "| Метод | NDCG@10 | NDCG@20 | Precision@10 | ProfitCapture@10 | MAE | MAPE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for _, row in frame.iterrows():
        is_catboost = row["method_id"] == "my_model"
        cells = [
            str(row["method"]),
            _format_metric(row.get("NDCG@10")),
            _format_metric(row.get("NDCG@20")),
            _format_percent(row.get("Precision@10")),
            _format_metric(row.get("ProfitCapture@10")),
            _format_money(row.get("MAE")),
            _format_percent(row.get("MAPE"), digits=2),
        ]
        if is_catboost:
            cells = [f"**{cell}**" for cell in cells]
        lines.append("| " + " | ".join(cells) + " |")

    ndcg_best = _best_method(frame, "NDCG@10")
    precision_best = _best_method(frame, "Precision@10")
    profit_best = _best_method(frame, "ProfitCapture@10")
    lines.extend(
        [
            "",
            "## Расшифровка результатов",
            "",
            (
                "Лучшее значение NDCG@10: "
                f"{ndcg_best[0]} ({_format_metric(ndcg_best[1])})."
                if ndcg_best
                else "Лучшее значение NDCG@10 не определено."
            ),
            "",
            _catboost_advantage_text(frame, "NDCG@10", "NDCG@10", percent_points=False),
            "",
            (
                "Лучшее значение Precision@10: "
                f"{precision_best[0]} ({_format_percent(precision_best[1])})."
                if precision_best
                else "Лучшее значение Precision@10 не определено."
            ),
            "",
            _catboost_advantage_text(frame, "Precision@10", "Precision@10", percent_points=True),
            "",
            (
                "Лучшее значение ProfitCapture@10: "
                f"{profit_best[0]} ({_format_metric(profit_best[1])})."
                if profit_best
                else "Лучшее значение ProfitCapture@10 не определено."
            ),
            "",
            _catboost_advantage_text(frame, "ProfitCapture@10", "ProfitCapture@10", percent_points=False),
            "",
            "Для инвестора это означает, что в текущей proxy-проверке верхняя часть списка лучше "
            "формируется статистическим и эвристическим baselines, а CatBoost не показывает "
            "преимущества по основным ranking-метрикам. Такой вывод нельзя переносить на "
            "реальную доходность сделок без независимых transaction prices или экспертной оценки "
            "рыночной цены.",
            "",
            "## Источник relevance",
            "",
            f"- Строк в control sample: {relevance_info.get('rows', 'не определено')}.",
            f"- `target_proxy_basis`: {', '.join(relevance_info.get('target_proxy_basis', [])) or 'не определено'}.",
            "- `target_proxy_price` совпадает с `listing_price`: "
            f"{'да' if relevance_info.get('target_proxy_price_equals_listing_price') else 'нет или не проверено'}.",
            f"- Объектов с положительной proxy-relevance: {relevance_info.get('positive_proxy_relevance_rows', 'не определено')}.",
            "",
            "## Статистическая значимость различий",
            "",
            TTEST_NOTE,
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    *,
    frame: pd.DataFrame,
    relevance_info: dict[str, Any],
    output_dir: Path,
    article_path: Path,
    metrics_path: Path,
    predictions_path: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "ranking_metrics_comparison.csv"
    json_path = output_dir / "ranking_metrics_comparison.json"

    frame.to_csv(csv_path, index=False)

    payload = {
        "source_files": {
            "metrics": str(metrics_path.relative_to(PROJECT_ROOT)),
            "predictions": str(predictions_path.relative_to(PROJECT_ROOT)),
        },
        "method_labels": METHOD_LABELS,
        "method_source_notes": METHOD_SOURCE_NOTES,
        "relevance_source": relevance_info,
        "statistical_significance": {
            "calculated": False,
            "reason": TTEST_NOTE,
        },
        "metrics": frame.where(pd.notna(frame), None).to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    article_path.write_text(build_article_markdown(frame, relevance_info), encoding="utf-8")
    return [csv_path, json_path, article_path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build article-ready ranking metrics comparison table.")
    parser.add_argument("--metrics-path", type=Path, default=DEFAULT_METRICS_PATH)
    parser.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--article-path", type=Path, default=DEFAULT_ARTICLE_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = _read_csv(args.metrics_path)
    predictions = _read_csv(args.predictions_path)
    frame = build_comparison_frame(metrics)
    relevance_info = inspect_relevance_source(predictions)
    generated = write_outputs(
        frame=frame,
        relevance_info=relevance_info,
        output_dir=args.output_dir,
        article_path=args.article_path,
        metrics_path=args.metrics_path,
        predictions_path=args.predictions_path,
    )
    print(json.dumps({"generated_files": [str(path) for path in generated]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
