from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from model.analytics.charts.common import ACCENT_COLOR, MAIN_COLOR, SECONDARY_COLOR, save_figure, style_axis


METHOD_LABELS = {
    "price_per_meter": "Price per meter",
    "formula": "Formula",
    "regression": "Regression",
    "my_model": "My model",
}
METHOD_COLORS = {
    "price_per_meter": MAIN_COLOR,
    "formula": SECONDARY_COLOR,
    "regression": ACCENT_COLOR,
    "my_model": "#7a5195",
}
VALUE_CHART_METHODS = ["price_per_meter", "formula", "my_model"]
RANKING_CHART_METHODS = ["price_per_meter", "formula", "regression", "my_model"]
RANKING_METHOD_LABELS = {
    "price_per_meter": "Статистический метод",
    "formula": "Эвристический скоринг",
    "regression": "Регрессионная модель",
    "my_model": "CatBoost",
}
RANKING_METHOD_STYLES = {
    "price_per_meter": {"facecolor": "white", "hatch": "///"},
    "formula": {"facecolor": "#d9d9d9", "hatch": "\\\\\\"},
    "regression": {"facecolor": "#8f8f8f", "hatch": "xxx"},
    "my_model": {"facecolor": "#4d4d4d", "hatch": "..."},
}
ERROR_CHART_METHODS = [
    ("price_per_meter", "price_per_meter_estimate"),
    ("formula", "formula_estimate"),
    ("my_model", "my_model_estimate"),
]


def _value_metric_rows(metrics_frame: pd.DataFrame) -> pd.DataFrame:
    return metrics_frame[metrics_frame["metric_layer"] == "value"].copy()


def save_value_metrics_chart(metrics_frame: pd.DataFrame, output_dir: Path) -> Path:
    values = _value_metric_rows(metrics_frame)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    metric_specs = [
        ("mae", "MAE, RUB"),
        ("rmse", "RMSE, RUB"),
        ("mape", "MAPE"),
    ]
    for ax, (metric_name, title) in zip(axes, metric_specs, strict=False):
        plot_values = values[["method", metric_name]].dropna()
        plot_values = plot_values[plot_values["method"].isin(VALUE_CHART_METHODS)]
        plot_values["method"] = pd.Categorical(
            plot_values["method"],
            categories=VALUE_CHART_METHODS,
            ordered=True,
        )
        plot_values = plot_values.sort_values("method")
        labels = [METHOD_LABELS.get(method, method) for method in plot_values["method"]]
        colors = [METHOD_COLORS.get(method, MAIN_COLOR) for method in plot_values["method"]]
        ax.bar(labels, plot_values[metric_name].astype(float), color=colors)
        ax.set_title(title)
        ax.tick_params(axis="x", labelrotation=20)
        style_axis(ax)
    fig.tight_layout()
    return save_figure(fig, output_dir / "mae_rmse_mape_comparison.png")


def save_predicted_vs_target_chart(
    comparison_frame: pd.DataFrame,
    *,
    estimate_column: str,
    method_label: str,
    output_path: Path,
) -> Path:
    values = comparison_frame[["target_proxy_price", estimate_column]].apply(pd.to_numeric, errors="coerce")
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    fig, ax = plt.subplots(figsize=(8, 8))
    if values.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
    else:
        ax.scatter(values["target_proxy_price"], values[estimate_column], s=16, alpha=0.35, color=MAIN_COLOR)
        lower = float(min(values["target_proxy_price"].min(), values[estimate_column].min()))
        upper = float(max(values["target_proxy_price"].max(), values[estimate_column].max()))
        ax.plot([lower, upper], [lower, upper], color=SECONDARY_COLOR, linewidth=1.5)
        if lower > 0:
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.set_xlabel("Proxy target на базе listing data, RUB")
        ax.set_ylabel(f"{method_label} estimate, RUB")
        style_axis(ax)
    ax.set_title(f"{method_label}: estimate vs proxy target")
    fig.tight_layout()
    return save_figure(fig, output_path)


def save_error_distribution_chart(comparison_frame: pd.DataFrame, output_dir: Path) -> Path:
    target = pd.to_numeric(comparison_frame["target_proxy_price"], errors="coerce")
    error_rows: list[pd.DataFrame] = []
    for method, estimate_column in ERROR_CHART_METHODS:
        estimate = pd.to_numeric(comparison_frame[estimate_column], errors="coerce")
        ape = ((estimate - target).abs() / target.replace({0: np.nan})).replace([np.inf, -np.inf], np.nan)
        error_rows.append(
            pd.DataFrame(
                {
                    "method": method,
                    "absolute_percentage_error": ape,
                }
            )
        )
    errors = pd.concat(error_rows, ignore_index=True).dropna()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    if errors.empty:
        for ax in axes:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
            ax.set_axis_off()
    else:
        clipped = errors.copy()
        if len(clipped) >= 20:
            clipped = clipped[clipped["absolute_percentage_error"] <= clipped["absolute_percentage_error"].quantile(0.99)]
        data = [
            clipped.loc[clipped["method"] == method, "absolute_percentage_error"].to_numpy()
            for method, _ in ERROR_CHART_METHODS
        ]
        axes[0].boxplot(data, labels=[METHOD_LABELS[method] for method, _ in ERROR_CHART_METHODS], showfliers=False)
        axes[0].set_title("APE по подходам")
        axes[0].set_ylabel("Absolute percentage error")
        axes[0].tick_params(axis="x", labelrotation=20)
        style_axis(axes[0])

        for method, _ in ERROR_CHART_METHODS:
            subset = clipped.loc[clipped["method"] == method, "absolute_percentage_error"]
            axes[1].hist(
                subset,
                bins=40,
                alpha=0.45,
                label=METHOD_LABELS[method],
                color=METHOD_COLORS[method],
            )
        axes[1].set_title("Распределение APE до p99")
        axes[1].set_xlabel("Absolute percentage error")
        axes[1].set_ylabel("Количество")
        axes[1].legend()
        style_axis(axes[1])
    fig.tight_layout()
    return save_figure(fig, output_dir / "error_distribution.png")


def save_ranking_comparison_chart(metrics_frame: pd.DataFrame, output_dir: Path) -> Path:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "text.color": "black",
            "axes.edgecolor": "black",
            "axes.labelcolor": "black",
            "xtick.color": "black",
            "ytick.color": "black",
        }
    )
    ranking = metrics_frame[
        (metrics_frame["metric_layer"] == "ranking")
        & (metrics_frame["metric"].isin(["ndcg", "precision", "profit_capture"]))
        & (
            ((metrics_frame["metric"] == "ndcg") & (metrics_frame["k"].isin([10, 20])))
            | ((metrics_frame["metric"].isin(["precision", "profit_capture"])) & (metrics_frame["k"] == 10))
        )
        & (metrics_frame["method"].isin(RANKING_CHART_METHODS))
    ].copy()
    fig, ax = plt.subplots(figsize=(12, 6.2), facecolor="white")
    ax.set_facecolor("white")
    if ranking.empty:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_axis_off()
    else:
        metric_specs = [
            ("ndcg", 10, "NDCG@10"),
            ("ndcg", 20, "NDCG@20"),
            ("precision", 10, "Precision@10"),
            ("profit_capture", 10, "ProfitCapture@10"),
        ]
        methods = RANKING_CHART_METHODS
        x = np.arange(len(metric_specs))
        width = 0.18
        max_value = 1.0
        for offset, method in enumerate(methods):
            values = []
            for metric, k_value, _ in metric_specs:
                metric_values = ranking[
                    (ranking["method"] == method)
                    & (ranking["metric"] == metric)
                    & (ranking["k"] == k_value)
                ]["value"]
                value = (
                    float(metric_values.iloc[0])
                    if not metric_values.empty and pd.notna(metric_values.iloc[0])
                    else np.nan
                )
                values.append(value)
                if np.isfinite(value):
                    max_value = max(max_value, value)
            style = RANKING_METHOD_STYLES[method]
            bars = ax.bar(
                x + (offset - (len(methods) - 1) / 2) * width,
                values,
                width=width,
                label=RANKING_METHOD_LABELS[method],
                color=style["facecolor"],
                edgecolor="black",
                linewidth=1.0,
                hatch=style["hatch"],
            )
            ax.bar_label(
                bars,
                labels=["" if not np.isfinite(value) else f"{value:.2f}" for value in values],
                padding=3,
                fontsize=9,
                color="black",
            )
        ax.set_xticks(x)
        ax.set_xticklabels([label for _, _, label in metric_specs])
        ax.set_ylim(0, min(1.15, max(1.05, max_value * 1.08)))
        ax.set_ylabel("Значение метрики, доля от 0 до 1")
        ax.set_title("Сравнение качества ранжирования объектов недвижимости")
        ax.tick_params(axis="both", labelsize=10, width=1.0)
        ax.yaxis.label.set_size(11)
        ax.title.set_size(14)
        ax.title.set_weight("bold")
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.12),
            ncol=2,
            frameon=False,
            fontsize=10,
            handlelength=2.8,
        )
        style_axis(ax)
        ax.grid(axis="y", color="#e0e0e0", linewidth=0.5)
        ax.grid(axis="x", visible=False)
        for spine in ax.spines.values():
            spine.set_color("black")
            spine.set_linewidth(1.0)
    fig.tight_layout()
    return save_figure(fig, output_dir / "ranking_comparison.png")


def save_valuation_comparison_charts(
    comparison_frame: pd.DataFrame,
    metrics_frame: pd.DataFrame,
    output_dir: Path,
) -> list[Path]:
    return [
        save_value_metrics_chart(metrics_frame, output_dir),
        save_predicted_vs_target_chart(
            comparison_frame,
            estimate_column="formula_estimate",
            method_label="Formula",
            output_path=output_dir / "predicted_vs_target_formula.png",
        ),
        save_predicted_vs_target_chart(
            comparison_frame,
            estimate_column="regression_estimate",
            method_label="Regression",
            output_path=output_dir / "predicted_vs_target_regression.png",
        ),
        save_predicted_vs_target_chart(
            comparison_frame,
            estimate_column="my_model_estimate",
            method_label="My model",
            output_path=output_dir / "predicted_vs_target_my_model.png",
        ),
        save_error_distribution_chart(comparison_frame, output_dir),
        save_ranking_comparison_chart(metrics_frame, output_dir),
    ]
