from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)

from model.ml.model.utils import ensure_directory


def compute_regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_array = np.asarray(y_true, dtype=float)
    y_pred_array = np.asarray(y_pred, dtype=float)

    return {
        "mae": float(mean_absolute_error(y_true_array, y_pred_array)),
        "rmse": float(np.sqrt(mean_squared_error(y_true_array, y_pred_array))),
        "r2": float(r2_score(y_true_array, y_pred_array)),
        "mape": float(mean_absolute_percentage_error(y_true_array, y_pred_array)),
    }


def save_target_distribution_plot(target: pd.Series, output_path: Path) -> None:
    ensure_directory(output_path.parent)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(target, bins=40, color="#4E79A7", edgecolor="white")
    axes[0].set_title("Распределение цены")
    axes[0].set_xlabel("price")

    axes[1].hist(np.log1p(target), bins=40, color="#F28E2B", edgecolor="white")
    axes[1].set_title("Распределение log1p(price)")
    axes[1].set_xlabel("log1p(price)")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def save_feature_importance_plot(
    feature_importance: pd.DataFrame,
    output_path: Path,
    top_n: int = 20,
) -> None:
    ensure_directory(output_path.parent)
    subset = feature_importance.head(top_n).iloc[::-1]

    fig, ax = plt.subplots(figsize=(10, max(6, len(subset) * 0.35)))
    ax.barh(subset["feature"], subset["importance"], color="#59A14F")
    ax.set_title(f"Top {len(subset)} Feature Importances")
    ax.set_xlabel("Importance")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def build_validation_report(
    model_name: str,
    metrics: dict[str, float],
    cv_metrics: dict[str, Any] | None = None,
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "validation_metrics": metrics,
        "cross_validation": cv_metrics or {},
        "notes": notes or {},
    }
