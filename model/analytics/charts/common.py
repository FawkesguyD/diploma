from __future__ import annotations

from pathlib import Path
from statistics import NormalDist

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from model.ml.model.utils import ensure_directory


MAIN_COLOR = "#2f6f8f"
SECONDARY_COLOR = "#c95f3d"
ACCENT_COLOR = "#5c8f3a"
GRID_COLOR = "#d7d7d7"


def save_figure(fig: plt.Figure, output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return output_path


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def positive_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = numeric_series(frame, column)
    return values[values > 0]


def annotate_bars(ax: plt.Axes, *, fmt: str = "{:.0f}") -> None:
    for patch in ax.patches:
        width = patch.get_width()
        if not np.isfinite(width):
            continue
        ax.text(
            width,
            patch.get_y() + patch.get_height() / 2,
            f" {fmt.format(width)}",
            va="center",
            fontsize=8,
        )


def sampled(values: pd.Series, max_points: int = 5_000, random_state: int = 42) -> pd.Series:
    values = values.dropna()
    if len(values) <= max_points:
        return values
    return values.sample(max_points, random_state=random_state)


def kde_line(values: pd.Series, points: int = 220) -> tuple[np.ndarray, np.ndarray] | None:
    sample = sampled(values, max_points=3_000)
    if len(sample) < 3:
        return None
    array = sample.to_numpy(dtype=float)
    std = float(np.std(array))
    if std <= 0:
        return None
    bandwidth = 1.06 * std * (len(array) ** (-1 / 5))
    if bandwidth <= 0:
        return None
    x_min, x_max = float(np.min(array)), float(np.max(array))
    grid = np.linspace(x_min, x_max, points)
    density = np.zeros_like(grid)
    chunk_size = 500
    for start in range(0, len(array), chunk_size):
        chunk = array[start : start + chunk_size]
        z = (grid[:, None] - chunk[None, :]) / bandwidth
        density += np.exp(-0.5 * z * z).sum(axis=1)
    density /= len(array) * bandwidth * np.sqrt(2 * np.pi)
    return grid, density


def qq_points(values: pd.Series, max_points: int = 5_000) -> tuple[np.ndarray, np.ndarray] | None:
    sample = sampled(values, max_points=max_points).dropna()
    if len(sample) < 3:
        return None
    ordered = np.sort(sample.to_numpy(dtype=float))
    std = float(np.std(ordered))
    if std <= 0:
        return None
    observed = (ordered - float(np.mean(ordered))) / std
    distribution = NormalDist()
    probabilities = (np.arange(1, len(observed) + 1) - 0.5) / len(observed)
    theoretical = np.array([distribution.inv_cdf(float(probability)) for probability in probabilities])
    return theoretical, observed


def style_axis(ax: plt.Axes) -> None:
    ax.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.65)
    ax.set_axisbelow(True)
