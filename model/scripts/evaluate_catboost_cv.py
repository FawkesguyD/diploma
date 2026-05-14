from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH, HF_DATASET_NAME, dataset_fingerprint, load_dataset_frame
from model.ml.model.training import (
    _build_catboost_model,
    _predict_log_target_model,
    _prepare_catboost_frame,
)
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports"
DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "ARTICLE_CROSS_VALIDATION.md"
CSV_OUTPUT_NAME = "catboost_cv_results.csv"
JSON_OUTPUT_NAME = "catboost_cv_results.json"


def compute_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_array = np.asarray(y_true, dtype=float)
    y_pred_array = np.asarray(y_pred, dtype=float)
    errors = y_true_array - y_pred_array
    non_zero_mask = y_true_array != 0
    denominator = np.sum(np.square(y_true_array - np.mean(y_true_array)))

    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "mape": float(np.mean(np.abs(errors[non_zero_mask] / y_true_array[non_zero_mask])) * 100),
        "r2": float(1 - np.sum(np.square(errors)) / denominator) if denominator else float("nan"),
    }


def run_catboost_cv(
    data_path: Path,
    n_splits: int,
    random_state: int,
    force_download: bool,
) -> dict[str, Any]:
    raw_df = load_dataset_frame(data_path, force_download=force_download)
    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)

    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    fold_rows: list[dict[str, Any]] = []

    for fold_index, (train_idx, valid_idx) in enumerate(splitter.split(X, y), start=1):
        model = _build_catboost_model()
        X_train = X.iloc[train_idx]
        X_valid = X.iloc[valid_idx]
        y_train = y.iloc[train_idx]
        y_valid = y.iloc[valid_idx]

        X_train_cat = _prepare_catboost_frame(X_train, feature_config)
        X_valid_cat = _prepare_catboost_frame(X_valid, feature_config)
        model.fit(
            X_train_cat,
            np.log1p(y_train),
            cat_features=feature_config.categorical_features,
            eval_set=(X_valid_cat, np.log1p(y_valid)),
            use_best_model=True,
            early_stopping_rounds=50,
            verbose=False,
        )
        predictions = _predict_log_target_model(model, X_valid_cat)
        fold_rows.append(
            {
                "fold": fold_index,
                "train_rows": int(len(train_idx)),
                "valid_rows": int(len(valid_idx)),
                **compute_metrics(y_valid, predictions),
            }
        )

    metric_names = ["mae", "rmse", "mape", "r2"]
    summary_rows = [
        {
            "fold": "mean",
            "train_rows": None,
            "valid_rows": None,
            **{
                metric: float(np.mean([row[metric] for row in fold_rows]))
                for metric in metric_names
            },
        },
        {
            "fold": "std",
            "train_rows": None,
            "valid_rows": None,
            **{
                metric: float(np.std([row[metric] for row in fold_rows]))
                for metric in metric_names
            },
        },
    ]

    return {
        "metadata": {
            "model_name": "catboost_regressor",
            "dataset_name": HF_DATASET_NAME,
            "dataset_path": str(data_path),
            "dataset_sha256": dataset_fingerprint(data_path) if data_path.exists() else None,
            "target_column": feature_config.target_column,
            "target_currency": "USD",
            "target_transform": "log1p",
            "inverse_transform": "expm1",
            "split_strategy": "random_kfold",
            "n_splits": n_splits,
            "shuffle": True,
            "random_state": random_state,
            "rows_before_cleaning": qc_summary["rows_before_cleaning"],
            "rows_after_cleaning": qc_summary["rows_after_cleaning"],
            "numerical_features": feature_config.numerical_features,
            "categorical_features": feature_config.categorical_features,
            "catboost_params": _build_catboost_model().get_params(),
            "mape_note": "Rows with y_true = 0 are excluded from MAPE denominator.",
        },
        "folds": fold_rows,
        "summary": {
            "mean": summary_rows[0],
            "std": summary_rows[1],
        },
        "rows": fold_rows + summary_rows,
    }


def save_csv(payload: dict[str, Any], output_path: Path) -> None:
    ensure_directory(output_path.parent)
    pd.DataFrame(payload["rows"]).to_csv(output_path, index=False)


def save_json(payload: dict[str, Any], output_path: Path) -> None:
    ensure_directory(output_path.parent)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def format_money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def format_percent(value: float) -> str:
    return f"{value:.2f}%".replace(".", ",")


def format_r2(value: float) -> str:
    return f"{value:.4f}".replace(".", ",")


def markdown_table(payload: dict[str, Any]) -> str:
    labels = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", "mean": "Среднее", "std": "Стандартное отклонение"}
    lines = [
        "| Фолд | MAE | RMSE | MAPE | R² |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {fold} | {mae} | {rmse} | {mape} | {r2} |".format(
                fold=labels[row["fold"]],
                mae=format_money(row["mae"]),
                rmse=format_money(row["rmse"]),
                mape=format_percent(row["mape"]),
                r2=format_r2(row["r2"]),
            )
        )
    return "\n".join(lines)


def build_interpretation(payload: dict[str, Any]) -> str:
    mean = payload["summary"]["mean"]
    std = payload["summary"]["std"]
    mae_cv = std["mae"] / mean["mae"] * 100 if mean["mae"] else float("nan")
    rmse_cv = std["rmse"] / mean["rmse"] * 100 if mean["rmse"] else float("nan")
    mape_std = std["mape"]
    r2_std = std["r2"]
    mae_cv_text = f"{mae_cv:.2f}".replace(".", ",")
    rmse_cv_text = f"{rmse_cv:.2f}".replace(".", ",")
    mape_std_text = f"{mape_std:.2f}".replace(".", ",")
    r2_std_text = f"{r2_std:.4f}".replace(".", ",")

    if max(mae_cv, rmse_cv) <= 10 and mape_std <= 2:
        return (
            "Результаты кросс-валидации показывают, что значения метрик на разных фолдах "
            "изменяются умеренно. Относительное стандартное отклонение MAE составляет "
            f"{mae_cv_text}%, RMSE - {rmse_cv_text}%, стандартное отклонение MAPE равно "
            f"{mape_std_text} п.п., а R² - {r2_std_text}, что указывает на устойчивость модели "
            "на разных частях выборки."
        )

    return (
        "Результаты кросс-валидации показывают заметную вариативность качества между фолдами. "
        "Относительное стандартное отклонение MAE составляет "
        f"{mae_cv_text}%, RMSE - {rmse_cv_text}%, стандартное отклонение MAPE равно "
        f"{mape_std_text} п.п., а R² - {r2_std_text}, поэтому устойчивость модели следует "
        "интерпретировать осторожно."
    )


def save_article(payload: dict[str, Any], output_path: Path) -> None:
    metadata = payload["metadata"]
    table = markdown_table(payload)
    after_table = build_interpretation(payload)
    content = f"""# Кросс-валидация CatBoost модели

## 1. Источник данных

Использовался датасет `{metadata["dataset_name"]}`, загруженный из `{metadata["dataset_path"]}`. Целевой переменной является `{metadata["target_column"]}` в USD, проверялась модель `CatBoostRegressor` из training pipeline проекта. При обучении использовалась схема `log1p(price)`, а прогнозы перед расчетом метрик возвращались в исходную шкалу через `expm1`.

## 2. Стратегия разбиения

Для проверки устойчивости модели была проведена кросс-валидация на 5 фолдах. В текущем эксперименте использовалась случайная стратегия разбиения, так как данные объявлений не были представлены как строгий временной ряд. Разбиение выполнялось с фиксированным `random_state=42`, что обеспечивает воспроизводимость результатов.

## 3. Таблица 4 - Результаты кросс-валидации CatBoost модели

{table}

## 4. Текст перед таблицей для статьи

Для оценки устойчивости модели была проведена кросс-валидация на 5 фолдах. Такой подход позволяет проверить, насколько качество модели зависит от конкретного разбиения обучающей выборки.

## 5. Текст после таблицы для статьи

{after_table}

## 6. Методологическое ограничение

Следует учитывать, что кросс-валидация проводилась на данных объявлений, а не на данных реальных сделок. Поэтому результаты отражают устойчивость proxy-valuation модели, но не являются прямым доказательством точности оценки фактической рыночной цены.
"""
    ensure_directory(output_path.parent)
    output_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="5-fold cross-validation для legacy CatBoost модели.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--article-path", type=Path, default=DEFAULT_ARTICLE_PATH)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_catboost_cv(
        data_path=args.data_path,
        n_splits=args.n_splits,
        random_state=args.random_state,
        force_download=args.force_download,
    )
    save_csv(payload, args.output_dir / CSV_OUTPUT_NAME)
    save_json(payload, args.output_dir / JSON_OUTPUT_NAME)
    save_article(payload, args.article_path)
    print(f"Saved CSV: {args.output_dir / CSV_OUTPUT_NAME}")
    print(f"Saved JSON: {args.output_dir / JSON_OUTPUT_NAME}")
    print(f"Saved article markdown: {args.article_path}")


if __name__ == "__main__":
    main()
