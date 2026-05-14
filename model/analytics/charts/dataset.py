from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patheffects as path_effects
import numpy as np
import pandas as pd

from model.analytics.charts.common import (
    ACCENT_COLOR,
    MAIN_COLOR,
    SECONDARY_COLOR,
    annotate_bars,
    numeric_series,
    save_figure,
    style_axis,
)


NUMERIC_CHARTS = [
    ("area", "Площадь, м²"),
    ("rooms", "Комнаты"),
    ("level", "Этаж"),
    ("levels", "Этажность дома"),
    ("year_built", "Год постройки"),
    ("price_per_m2", "Цена за м², RUB"),
]

CORRELATION_LABELS = {
    "rooms": "Комнаты",
    "area": "Площадь",
    "kitchen_area": "Площадь кухни",
    "level": "Этаж",
    "levels": "Этажность дома",
    "year_built": "Год постройки",
    "latitude": "Широта",
    "longitude": "Долгота",
    "price": "Цена",
    "price_per_m2": "Цена за м²",
}


def _draw_hist_or_empty(ax: plt.Axes, frame: pd.DataFrame, column: str, title: str) -> None:
    values = numeric_series(frame, column)
    if values.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_title(title)
        return
    ax.hist(values, bins=min(50, max(10, int(np.sqrt(len(values))))), color=MAIN_COLOR, edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(title)
    ax.set_ylabel("Количество")
    style_axis(ax)


def save_numeric_distribution_charts(frame: pd.DataFrame, output_dir: Path) -> Path:
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    for ax, (column, title) in zip(axes.ravel(), NUMERIC_CHARTS):
        if column == "rooms" and column in frame.columns:
            counts = frame[column].dropna().astype(int).value_counts().sort_index()
            if counts.empty:
                ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            else:
                ax.bar(counts.index.astype(str), counts.values, color=SECONDARY_COLOR)
                ax.set_title(title)
                ax.set_xlabel("Комнаты")
                ax.set_ylabel("Количество")
                style_axis(ax)
            continue
        _draw_hist_or_empty(ax, frame, column, title)
    fig.suptitle("Распределения ключевых числовых признаков", fontsize=15)
    fig.tight_layout()
    return save_figure(fig, output_dir / "dataset_numeric_distributions.png")


def save_numeric_boxplots(frame: pd.DataFrame, output_dir: Path) -> Path:
    columns = [
        ("area", "Площадь"),
        ("kitchen_area", "Кухня"),
        ("level", "Этаж"),
        ("levels", "Этажность"),
        ("year_built", "Год постройки"),
        ("price_per_m2", "Цена за м²"),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(14, 10))
    for ax, (column, title) in zip(axes.ravel(), columns):
        values = numeric_series(frame, column)
        if values.empty:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.set_title(title)
            continue
        ax.boxplot(values, vert=False, showfliers=False, patch_artist=True, boxprops={"facecolor": ACCENT_COLOR})
        ax.set_title(f"{title}: boxplot без выбросов")
        ax.set_xlabel(title)
        style_axis(ax)
    fig.suptitle("Устойчивый обзор разброса числовых признаков", fontsize=15)
    fig.tight_layout()
    return save_figure(fig, output_dir / "dataset_numeric_boxplots.png")


def save_rooms_price_violin(frame: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    source = frame[["rooms", "price_per_m2"]].dropna().copy()
    source = source[(source["rooms"] >= 0) & (source["rooms"] <= 6) & (source["price_per_m2"] > 0)]
    groups = []
    labels = []
    for rooms, group in source.groupby(source["rooms"].astype(int)):
        if len(group) < 5:
            continue
        groups.append(group["price_per_m2"].to_numpy(dtype=float))
        labels.append(str(rooms))

    if not groups:
        ax.text(0.5, 0.5, "Недостаточно данных", ha="center", va="center")
    else:
        parts = ax.violinplot(groups, showmedians=True, showextrema=False)
        for body in parts["bodies"]:
            body.set_facecolor(MAIN_COLOR)
            body.set_edgecolor("white")
            body.set_alpha(0.75)
        parts["cmedians"].set_color(SECONDARY_COLOR)
        ax.set_xticks(range(1, len(labels) + 1), labels)
        ax.set_xlabel("Комнаты")
        ax.set_ylabel("Цена за м², RUB")
        style_axis(ax)
    ax.set_title("Распределение цены за м² по комнатности")
    fig.tight_layout()
    return save_figure(fig, output_dir / "dataset_price_m2_by_rooms_violin.png")


def save_correlation_heatmap(frame: pd.DataFrame, output_dir: Path) -> Path:
    columns = [
        "rooms",
        "area",
        "kitchen_area",
        "level",
        "levels",
        "year_built",
        "latitude",
        "longitude",
        "price",
        "price_per_m2",
    ]
    numeric = frame[[column for column in columns if column in frame.columns]].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=1, thresh=max(3, int(len(numeric) * 0.05)))
    numeric = numeric.loc[:, [column for column in numeric.columns if numeric[column].nunique(dropna=True) > 1]]

    fig, ax = plt.subplots(figsize=(10, 8))
    if numeric.shape[1] < 2:
        ax.text(0.5, 0.5, "Недостаточно числовых признаков", ha="center", va="center")
        ax.set_axis_off()
    else:
        corr = numeric.corr()
        labels = [CORRELATION_LABELS.get(column, column) for column in corr.columns]
        cmap = LinearSegmentedColormap.from_list(
            "black_white_correlation",
            ["#1a1a1a", "#f2f2f2", "#1a1a1a"],
        )
        image = ax.imshow(corr, cmap=cmap, vmin=-1, vmax=1)
        ax.set_facecolor("white")
        fig.patch.set_facecolor("white")
        ax.set_xticks(range(len(corr.columns)), labels, rotation=45, ha="right")
        ax.set_yticks(range(len(corr.columns)), labels)
        ax.set_xticks(np.arange(-0.5, len(corr.columns), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(corr.columns), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.2)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.tick_params(axis="both", colors="black")
        for i in range(len(corr.columns)):
            for j in range(len(corr.columns)):
                text = ax.text(
                    j,
                    i,
                    f"{corr.iloc[i, j]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                )
                text.set_path_effects([path_effects.withStroke(linewidth=1.4, foreground="black")])
        colorbar = fig.colorbar(image, ax=ax, shrink=0.8)
        colorbar.ax.tick_params(colors="black")
    ax.set_title("Корреляции полезных числовых полей")
    fig.tight_layout()
    return save_figure(fig, output_dir / "dataset_numeric_correlation.png")


def save_category_top_charts(frame: pd.DataFrame, output_dir: Path, top_n: int = 15) -> Path:
    columns = [
        ("building_type", "Тип дома"),
        ("object_type", "Тип объекта"),
        ("region", "Регион"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, (column, title) in zip(axes.ravel(), columns):
        if column not in frame.columns:
            ax.text(0.5, 0.5, "Нет поля", ha="center", va="center")
            ax.set_title(title)
            continue
        counts = frame[column].dropna().astype(str).value_counts().head(top_n).sort_values()
        if counts.empty:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.set_title(title)
            continue
        ax.barh(counts.index, counts.values, color=ACCENT_COLOR)
        ax.set_title(title)
        ax.set_xlabel("Количество")
        annotate_bars(ax)
        style_axis(ax)
    fig.suptitle("Топ категорий из нормализованного слоя", fontsize=15)
    fig.tight_layout()
    return save_figure(fig, output_dir / "dataset_top_categories.png")


def save_dataset_charts(frame: pd.DataFrame, output_dir: Path, top_n: int = 15) -> list[Path]:
    return [
        save_numeric_distribution_charts(frame, output_dir),
        save_numeric_boxplots(frame, output_dir),
        save_rooms_price_violin(frame, output_dir),
        save_correlation_heatmap(frame, output_dir),
        save_category_top_charts(frame, output_dir, top_n=top_n),
    ]
