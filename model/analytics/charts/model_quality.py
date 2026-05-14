from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from model.analytics.charts.common import MAIN_COLOR, SECONDARY_COLOR, save_figure, style_axis
from model.analytics.config import AnalyticsConfig
from model.ml.model.evaluate import compute_regression_metrics
from model.ml.model.inference import predict_proxy_valuation_from_bundle
from model.ml.model.persistence import LoadedModelBundle, load_model_bundle
from model.ml.model.readiness import ModelReadinessError, load_ready_model_bundle


def load_inference_bundle(config: AnalyticsConfig) -> tuple[LoadedModelBundle, str]:
    try:
        bundle = load_ready_model_bundle(
            configured_model_path=config.model_path,
            manifest_path=config.readiness_path,
            model_path_is_explicit=config.model_path_is_explicit,
        )
        return bundle, f"readiness:{config.readiness_path}"
    except ModelReadinessError:
        bundle = load_model_bundle(config.model_path)
        return bundle, f"joblib:{config.model_path}"


def _row_to_payload(row: pd.Series) -> dict[str, Any]:
    payload = {
        "listing_id": row.get("listing_id"),
        "listing_price": row.get("price"),
        "listing_currency": row.get("listing_currency") or "RUB",
        "rooms": row.get("rooms"),
        "area": row.get("area"),
        "total_area_m2": row.get("area"),
        "kitchen_area": row.get("kitchen_area"),
        "kitchen_area_m2": row.get("kitchen_area"),
        "level": row.get("level"),
        "floor": row.get("level"),
        "levels": row.get("levels"),
        "total_floors": row.get("levels"),
        "building_type": row.get("building_type"),
        "object_type": row.get("object_type"),
        "region": row.get("region"),
        "district": row.get("district"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }
    return {key: value for key, value in payload.items() if pd.notna(value)}


def score_model_quality(frame: pd.DataFrame, config: AnalyticsConfig) -> dict[str, Any]:
    bundle, model_source = load_inference_bundle(config)
    evaluation_source = frame[
        (frame["is_train_eligible"])
        & (frame["price"].notna())
        & (frame["price"] > 0)
        & (frame["area"].notna())
        & (frame["area"] > 0)
    ].copy()
    if evaluation_source.empty:
        return {
            "model_source": model_source,
            "metrics": {},
            "predictions": pd.DataFrame(),
            "skipped_rows": 0,
            "warning": "Нет строк с целевой ценой и площадью для оценки качества.",
        }

    if len(evaluation_source) > config.eval_max_rows:
        evaluation_source = evaluation_source.sample(config.eval_max_rows, random_state=config.random_state)

    rows: list[dict[str, Any]] = []
    skipped_rows = 0
    first_errors: list[str] = []
    for _, row in evaluation_source.iterrows():
        payload = _row_to_payload(row)
        try:
            result = predict_proxy_valuation_from_bundle(
                payload,
                bundle,
                output_currency="RUB",
                include_explanation=False,
            )
        except Exception as exc:
            skipped_rows += 1
            if len(first_errors) < 5:
                first_errors.append(str(exc))
            continue
        actual = float(row["price"])
        predicted = float(result["predicted_price_rub"])
        residual = predicted - actual
        rows.append(
            {
                "listing_id": row.get("listing_id"),
                "actual": actual,
                "predicted": predicted,
                "residual": residual,
                "abs_error": abs(residual),
                "absolute_percentage_error": abs(residual) / actual if actual else np.nan,
            }
        )

    predictions = pd.DataFrame(rows)
    if predictions.empty:
        return {
            "model_source": model_source,
            "metrics": {},
            "predictions": predictions,
            "skipped_rows": skipped_rows,
            "first_errors": first_errors,
            "warning": "Все строки были отклонены inference validation.",
        }

    metrics = compute_regression_metrics(predictions["actual"], predictions["predicted"].to_numpy())
    metrics["rows_evaluated"] = int(len(predictions))
    metrics["rows_skipped"] = int(skipped_rows)
    return {
        "model_source": model_source,
        "bundle_metrics": bundle.metrics,
        "metrics": metrics,
        "predictions": predictions,
        "skipped_rows": skipped_rows,
        "first_errors": first_errors,
    }


def save_predicted_vs_actual(predictions: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 8))
    if predictions.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
    else:
        ax.scatter(predictions["actual"], predictions["predicted"], s=12, alpha=0.28, color=MAIN_COLOR)
        lower = min(predictions["actual"].min(), predictions["predicted"].min())
        upper = max(predictions["actual"].max(), predictions["predicted"].max())
        ax.plot([lower, upper], [lower, upper], color=SECONDARY_COLOR, linewidth=1.5, label="Идеальное попадание")
        if lower > 0:
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.set_xlabel("Фактическая цена, RUB")
        ax.set_ylabel("Предсказанная цена, RUB")
        ax.legend()
        style_axis(ax)
    ax.set_title("Предсказанная цена vs фактическая цена")
    fig.tight_layout()
    return save_figure(fig, output_dir / "model_predicted_vs_actual.png")


def save_residuals_plot(predictions: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 6))
    if predictions.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
    else:
        ax.scatter(predictions["predicted"], predictions["residual"], s=12, alpha=0.28, color=MAIN_COLOR)
        ax.axhline(0, color=SECONDARY_COLOR, linewidth=1.5)
        ax.set_xlabel("Предсказанная цена, RUB")
        ax.set_ylabel("Ошибка, RUB")
        style_axis(ax)
    ax.set_title("Ошибки: прогноз vs ошибка")
    fig.tight_layout()
    return save_figure(fig, output_dir / "model_residuals.png")


def save_error_distribution(predictions: pd.DataFrame, output_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    if predictions.empty:
        for ax in axes:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.set_axis_off()
    else:
        axes[0].hist(predictions["residual"], bins=50, color=MAIN_COLOR, edgecolor="white")
        axes[0].axvline(0, color=SECONDARY_COLOR, linewidth=1.5)
        axes[0].set_title("Распределение ошибок")
        axes[0].set_xlabel("Прогноз - факт, RUB")
        axes[0].set_ylabel("Количество")
        style_axis(axes[0])

        ape = predictions["absolute_percentage_error"].replace([np.inf, -np.inf], np.nan).dropna()
        ape = ape[ape <= ape.quantile(0.99)] if len(ape) >= 20 else ape
        axes[1].hist(ape, bins=50, color=SECONDARY_COLOR, edgecolor="white")
        axes[1].set_title("Абсолютная процентная ошибка до p99")
        axes[1].set_xlabel("APE")
        axes[1].set_ylabel("Количество")
        style_axis(axes[1])
    fig.tight_layout()
    return save_figure(fig, output_dir / "model_error_distribution.png")


def save_model_quality_charts(predictions: pd.DataFrame, output_dir: Path) -> list[Path]:
    return [
        save_predicted_vs_actual(predictions, output_dir),
        save_residuals_plot(predictions, output_dir),
        save_error_distribution(predictions, output_dir),
    ]
