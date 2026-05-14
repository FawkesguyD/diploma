from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from model.analytics.charts.common import (
    MAIN_COLOR,
    SECONDARY_COLOR,
    kde_line,
    positive_series,
    qq_points,
    save_figure,
    style_axis,
)


def _hist_with_kde(ax: plt.Axes, values: pd.Series, title: str, xlabel: str) -> None:
    if values.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_title(title)
        return
    ax.hist(values, bins=50, density=True, color=MAIN_COLOR, alpha=0.72, edgecolor="white")
    density = kde_line(values)
    if density is not None:
        grid, y = density
        ax.plot(grid, y, color=SECONDARY_COLOR, linewidth=2, label="Оценка плотности")
        ax.legend()
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Плотность")
    style_axis(ax)


def save_price_distribution_charts(frame: pd.DataFrame, output_dir: Path) -> Path:
    price = positive_series(frame, "price")
    log_price = np.log(price) if not price.empty else pd.Series(dtype=float)
    raw_visible = price[price <= price.quantile(0.99)] if len(price) >= 20 else price

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    _hist_with_kde(
        axes[0],
        raw_visible,
        "Исходная цена: распределение до p99",
        "Цена, RUB",
    )
    _hist_with_kde(
        axes[1],
        pd.Series(log_price),
        "log(price): распределение",
        "log(price)",
    )
    fig.suptitle("Нормальность и длинный хвост распределения цен", fontsize=15)
    fig.tight_layout()
    return save_figure(fig, output_dir / "price_distribution_raw_log.png")


def save_price_qq_plots(frame: pd.DataFrame, output_dir: Path) -> Path:
    price = positive_series(frame, "price")
    log_price = pd.Series(np.log(price)) if not price.empty else pd.Series(dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, values, title in [
        (axes[0], price, "Q-Q график: исходная цена"),
        (axes[1], log_price, "Q-Q график: log(price)"),
    ]:
        points = qq_points(values)
        if points is None:
            ax.text(0.5, 0.5, "Недостаточно данных", ha="center", va="center")
            ax.set_title(title)
            continue
        theoretical, observed = points
        ax.scatter(theoretical, observed, s=8, alpha=0.35, color=MAIN_COLOR)
        lower = min(theoretical.min(), observed.min())
        upper = max(theoretical.max(), observed.max())
        ax.plot([lower, upper], [lower, upper], color=SECONDARY_COLOR, linewidth=1.5)
        ax.set_title(title)
        ax.set_xlabel("Теоретические квантили N(0, 1)")
        ax.set_ylabel("Наблюдаемые стандартизированные квантили")
        style_axis(ax)
    fig.tight_layout()
    return save_figure(fig, output_dir / "price_qq_raw_log.png")


def price_distribution_stats(frame: pd.DataFrame) -> dict[str, float | int | None]:
    price = positive_series(frame, "price")
    if price.empty:
        return {
            "count": 0,
            "price_skew": None,
            "price_kurtosis": None,
            "log_price_skew": None,
            "log_price_kurtosis": None,
        }
    log_price = pd.Series(np.log(price))
    return {
        "count": int(len(price)),
        "price_mean": float(price.mean()),
        "price_median": float(price.median()),
        "price_skew": float(price.skew()),
        "price_kurtosis": float(price.kurtosis()),
        "log_price_skew": float(log_price.skew()),
        "log_price_kurtosis": float(log_price.kurtosis()),
    }


def save_price_charts(frame: pd.DataFrame, output_dir: Path) -> list[Path]:
    return [
        save_price_distribution_charts(frame, output_dir),
        save_price_qq_plots(frame, output_dir),
    ]
