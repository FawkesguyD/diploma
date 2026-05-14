from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from model.analytics.charts.common import MAIN_COLOR, annotate_bars, save_figure, style_axis


def save_top_districts_chart(frame: pd.DataFrame, output_dir: Path, top_n: int = 20) -> Path:
    fig, ax = plt.subplots(figsize=(12, max(6, top_n * 0.35)))
    if "district_group" not in frame.columns:
        ax.text(0.5, 0.5, "Нет поля района", ha="center", va="center")
        ax.set_axis_off()
    else:
        counts = (
            frame["district_group"]
            .fillna("Не указан")
            .astype(str)
            .str.strip()
            .replace("", "Не указан")
            .value_counts()
            .head(top_n)
            .sort_values()
        )
        if counts.empty:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.set_axis_off()
        else:
            ax.barh(counts.index, counts.values, color=MAIN_COLOR)
            annotate_bars(ax)
            ax.set_xlabel("Количество объектов")
            ax.set_ylabel("Район или резервная группа")
            style_axis(ax)
    ax.set_title(f"Топ-{top_n} районов по количеству объектов")
    fig.tight_layout()
    return save_figure(fig, output_dir / "district_top_counts.png")
