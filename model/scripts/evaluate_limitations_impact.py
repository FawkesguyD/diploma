from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import KFold, train_test_split

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.data_loading import DEFAULT_LOCAL_DATASET_PATH, HF_DATASET_NAME, dataset_fingerprint, load_dataset_frame
from model.ml.model.training import _build_catboost_model, _predict_log_target_model, _prepare_catboost_frame
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.utils import PROJECT_ROOT, RANDOM_STATE, ensure_directory


DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "ARTICLE_LIMITATIONS_SENSITIVITY.md"
DEFAULT_IMPACT_PATH = DEFAULT_REPORTS_DIR / "limitations_impact_matrix.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_REPORTS_DIR / "limitations_sensitivity_summary.json"
DEFAULT_FEATURE_ABLATION_PATH = DEFAULT_REPORTS_DIR / "feature_ablation_results.csv"
DEFAULT_HYPERPARAMETER_PATH = DEFAULT_REPORTS_DIR / "hyperparameter_sensitivity_results.csv"


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


def evaluate_cv(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    n_splits: int,
    random_state: int,
) -> dict[str, float]:
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    fold_metrics: list[dict[str, float]] = []
    catboost_params = _build_catboost_model().get_params()

    for train_idx, valid_idx in splitter.split(X, y):
        model = CatBoostRegressor(**catboost_params)
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
        fold_metrics.append(compute_metrics(y_valid, predictions))

    return {
        metric: float(np.mean([fold[metric] for fold in fold_metrics]))
        for metric in fold_metrics[0]
    }


def validation_predictions(
    X: pd.DataFrame,
    y: pd.Series,
    raw_aligned: pd.DataFrame,
    feature_config: Any,
    test_size: float,
    random_state: int,
) -> tuple[pd.Series, pd.Series, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
    )
    catboost_params = _build_catboost_model().get_params()
    model = CatBoostRegressor(**catboost_params)
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
    predictions = pd.Series(
        _predict_log_target_model(model, X_valid_cat),
        index=y_valid.index,
        dtype=float,
    )
    metrics = compute_metrics(y_valid, predictions.to_numpy())
    return y_valid, predictions, raw_aligned.loc[y_valid.index].copy(), X_valid, metrics


def evaluate_holdout(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    test_size: float,
    random_state: int,
) -> dict[str, float]:
    raw_placeholder = pd.DataFrame(index=X.index)
    _, _, _, _, metrics = validation_predictions(
        X=X,
        y=y,
        raw_aligned=raw_placeholder,
        feature_config=feature_config,
        test_size=test_size,
        random_state=random_state,
    )
    return metrics


def out_of_fold_predictions(
    X: pd.DataFrame,
    y: pd.Series,
    feature_config: Any,
    n_splits: int,
    random_state: int,
) -> pd.Series:
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    predictions = pd.Series(index=y.index, dtype=float)
    catboost_params = _build_catboost_model().get_params()

    for train_idx, valid_idx in splitter.split(X, y):
        model = CatBoostRegressor(**catboost_params)
        X_train = X.iloc[train_idx]
        X_valid = X.iloc[valid_idx]
        y_train = y.iloc[train_idx]
        X_train_cat = _prepare_catboost_frame(X_train, feature_config)
        X_valid_cat = _prepare_catboost_frame(X_valid, feature_config)
        model.fit(
            X_train_cat,
            np.log1p(y_train),
            cat_features=feature_config.categorical_features,
            verbose=False,
        )
        predictions.iloc[valid_idx] = _predict_log_target_model(model, X_valid_cat)

    return predictions


def fmt_int(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def fmt_float(value: float, digits: int = 2) -> str:
    if abs(value) < 0.5 * (10 ** -digits):
        value = 0.0
    return f"{value:.{digits}f}".replace(".", ",")


def fmt_r2(value: float) -> str:
    if abs(value) < 0.00005:
        value = 0.0
    return f"{value:.4f}".replace(".", ",")


def fmt_mape(value: float) -> str:
    return f"{fmt_float(value, 2)}%"


def metric_table_row(row: pd.Series) -> str:
    return (
        f"| {row['Удаленный признак/группа']} | {fmt_mape(row['MAPE'])} | "
        f"{fmt_float(row['ΔMAPE, п.п.'], 2)} | {fmt_r2(row['R²'])} | {fmt_r2(row['ΔR²'])} |"
    )


def hyper_table_row(row: pd.Series) -> str:
    value_text = format_parameter_value(row["Значение"])
    return (
        f"| {row['Параметр']} | {value_text} | {fmt_mape(row['MAPE'])} | "
        f"{fmt_float(row['ΔMAPE, п.п.'], 2)} | {fmt_r2(row['R²'])} | {fmt_r2(row['ΔR²'])} |"
    )


def format_parameter_value(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return fmt_float(numeric, 4).rstrip("0").rstrip(",")


def label_for_text(label: str) -> str:
    if label.startswith("Группа: "):
        return "группы " + label.removeprefix("Группа: ")
    if label.startswith("Признак: "):
        return "признака " + label.removeprefix("Признак: ")
    return label


def metrics_for_mask(
    y: pd.Series,
    predictions: pd.Series,
    mask: pd.Series,
    min_count: int,
) -> dict[str, Any]:
    mask = mask.reindex(y.index).fillna(False).astype(bool)
    count = int(mask.sum())
    if count < min_count:
        return {
            "calculated": False,
            "count": count,
            "reason": f"недостаточно объектов для надежной оценки, минимум {min_count}",
        }
    return {
        "calculated": True,
        "count": count,
        "metrics": compute_metrics(y.loc[mask], predictions.loc[mask].to_numpy()),
    }


def district_metrics(
    raw_aligned: pd.DataFrame,
    y: pd.Series,
    predictions: pd.Series,
    min_count: int,
) -> dict[str, Any]:
    if "district" not in raw_aligned.columns:
        return {"calculated": False, "reason": "в данных нет поля district"}

    rows: list[dict[str, Any]] = []
    districts = raw_aligned["district"].fillna("missing")
    for district, group_index in districts.groupby(districts).groups.items():
        index = pd.Index(group_index)
        if len(index) < min_count:
            continue
        metrics = compute_metrics(y.loc[index], predictions.loc[index].to_numpy())
        rows.append({"district": district, "count": int(len(index)), **metrics})

    if not rows:
        return {
            "calculated": False,
            "reason": f"нет районов с количеством объектов не меньше {min_count}",
        }

    frame = pd.DataFrame(rows).sort_values("mape", ascending=False, ignore_index=True)
    return {
        "calculated": True,
        "min_count": min_count,
        "district_count": int(len(frame)),
        "mape_min": float(frame["mape"].min()),
        "mape_max": float(frame["mape"].max()),
        "mape_std": float(frame["mape"].std(ddof=0)),
        "r2_min": float(frame["r2"].min()),
        "r2_max": float(frame["r2"].max()),
        "r2_std": float(frame["r2"].std(ddof=0)),
        "top_worst_mape": frame.head(10).to_dict(orient="records"),
    }


def parsed_at_drift_summary(raw_aligned: pd.DataFrame) -> dict[str, Any]:
    if "parsed_at" not in raw_aligned.columns:
        return {"calculated": False, "reason": "в данных нет временного поля"}

    parsed_at = pd.to_datetime(raw_aligned["parsed_at"], errors="coerce")
    valid = parsed_at.dropna()
    if valid.empty:
        return {"calculated": False, "reason": "временное поле parsed_at не удалось разобрать"}

    span_days = float((valid.max() - valid.min()).total_seconds() / 86400)
    if span_days < 30:
        return {
            "calculated": False,
            "reason": "период наблюдений слишком короткий для оценки рыночного дрифта",
            "min_timestamp": valid.min().isoformat(),
            "max_timestamp": valid.max().isoformat(),
            "span_days": span_days,
        }

    return {
        "calculated": False,
        "reason": "требуется отдельная временная валидация, текущий скрипт не нашел достаточной периодизации",
        "min_timestamp": valid.min().isoformat(),
        "max_timestamp": valid.max().isoformat(),
        "span_days": span_days,
    }


def outlier_sensitivity(
    raw_df: pd.DataFrame,
    baseline_metrics: dict[str, float],
    strategy: str,
    n_splits: int,
    test_size: float,
    random_state: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for quantile in [0.99, 0.95]:
        threshold = float(raw_df["price_usd"].quantile(quantile))
        filtered_raw = raw_df[raw_df["price_usd"] <= threshold].copy()
        X_filtered, y_filtered, filtered_config, filtered_qc = prepare_training_frame(filtered_raw)
        if strategy == "holdout":
            filtered_metrics = evaluate_holdout(
                X_filtered,
                y_filtered,
                filtered_config,
                test_size,
                random_state,
            )
        else:
            filtered_metrics = evaluate_cv(X_filtered, y_filtered, filtered_config, n_splits, random_state)
        key = f"upper_{int((1 - quantile) * 100)}pct_removed"
        result[key] = {
            "price_threshold": threshold,
            "rows_before_cleaning": filtered_qc["rows_before_cleaning"],
            "rows_after_cleaning": filtered_qc["rows_after_cleaning"],
            "metrics": filtered_metrics,
            "delta_vs_baseline": {
                metric: filtered_metrics[metric] - baseline_metrics[metric]
                for metric in baseline_metrics
            },
        }
    return result


def best_ablation_impact(ablation: pd.DataFrame) -> dict[str, Any]:
    candidates = ablation[ablation["Удаленный признак/группа"] != "baseline"].copy()
    if candidates.empty:
        return {"calculated": False, "reason": "нет строк ablation analysis"}
    candidates = candidates.sort_values("ΔMAPE, п.п.", ascending=False, ignore_index=True)
    best = candidates.iloc[0]
    return {
        "calculated": True,
        "label": str(best["Удаленный признак/группа"]),
        "delta_mape_pp": float(best["ΔMAPE, п.п."]),
        "delta_r2": float(best["ΔR²"]),
    }


def make_impact_matrix(summary: dict[str, Any]) -> list[dict[str, str]]:
    ablation = summary["feature_ablation_impact"]
    geography = summary["geography"]
    outliers = summary["outliers"]
    missing = summary["missing_data"]

    if ablation["calculated"] and ablation["delta_mape_pp"] > 0:
        missing_features_impact = (
            f"+{fmt_float(ablation['delta_mape_pp'], 2)} п.п. к MAPE "
            f"при удалении {label_for_text(ablation['label'])}"
        )
    else:
        missing_features_impact = "не рассчитано количественно"

    if geography["calculated"]:
        geo_impact = (
            f"MAPE по районам от {fmt_mape(geography['mape_min'])} до "
            f"{fmt_mape(geography['mape_max'])}, R² от {fmt_r2(geography['r2_min'])} "
            f"до {fmt_r2(geography['r2_max'])}, районов с n>=50: {geography['district_count']}"
        )
    else:
        geo_impact = "не рассчитано количественно"

    upper_1 = outliers["upper_1pct_removed"]
    outlier_delta = -float(upper_1["delta_vs_baseline"]["mape"])
    if outlier_delta > 0:
        outlier_impact = f"+{fmt_float(outlier_delta, 2)} п.п. к MAPE относительно выборки без верхнего 1% цен"
    else:
        outlier_impact = (
            f"{fmt_float(float(upper_1['delta_vs_baseline']['mape']), 2)} п.п. к MAPE "
            "после удаления верхнего 1% цен"
        )

    if missing["calculated"] and missing["complete"]["calculated"] and missing["high_missing"]["calculated"]:
        delta_mape = missing["high_missing"]["metrics"]["mape"] - missing["complete"]["metrics"]["mape"]
        missing_impact = (
            f"+{fmt_float(delta_mape, 2)} п.п. к MAPE у объектов с большим числом пропусков "
            "относительно объектов без пропусков"
            if delta_mape >= 0
            else f"{fmt_float(delta_mape, 2)} п.п. к MAPE у объектов с большим числом пропусков"
        )
    elif missing["calculated"] and not missing["complete"]["calculated"]:
        missing_impact = (
            "не рассчитано количественно, объектов без пропусков "
            f"{missing['complete']['count']} < 50"
        )
    else:
        missing_impact = "не рассчитано количественно"

    drift = summary["drift"]
    drift_impact = "не рассчитано количественно"
    if drift.get("span_days") is not None:
        drift_impact += f", период наблюдений {fmt_float(drift['span_days'], 2)} дня"

    return [
        {
            "Ограничение": "Данные объявлений вместо данных сделок",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Использовать данные фактических сделок или экспертную оценку рыночной цены.",
        },
        {
            "Ограничение": "Пропущенные признаки",
            "Влияние на точность": missing_features_impact,
            "Способ смягчения": "Сбор дополнительных данных и расширение признакового пространства.",
        },
        {
            "Ограничение": "Дрифт данных",
            "Влияние на точность": drift_impact,
            "Способ смягчения": "Мониторинг распределений признаков и регулярное переобучение модели.",
        },
        {
            "Ограничение": "Географическая неоднородность рынка",
            "Влияние на точность": geo_impact,
            "Способ смягчения": "Отдельные региональные модели или добавление более точных географических признаков.",
        },
        {
            "Ограничение": "Выбросы в ценах",
            "Влияние на точность": outlier_impact,
            "Способ смягчения": "Фильтрация аномалий, robust preprocessing или winsorization.",
        },
        {
            "Ограничение": "Пропуски в данных",
            "Влияние на точность": missing_impact,
            "Способ смягчения": "Улучшение парсинга, imputing и контроль качества данных.",
        },
        {
            "Ограничение": "Отсутствие признаков о ремонте / юридическом статусе / инфраструктуре",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Сбор дополнительных данных из описания, NLP-анализ текста и подключение внешних источников.",
        },
    ]


def markdown_impact_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| Ограничение | Влияние на точность | Способ смягчения |",
        "|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['Ограничение']} | {row['Влияние на точность']} | {row['Способ смягчения']} |"
        )
    return "\n".join(lines)


def markdown_feature_table(feature_rows: pd.DataFrame) -> str:
    lines = [
        "| Удаленный признак/группа | MAPE | ΔMAPE, п.п. | R² | ΔR² |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in feature_rows.iterrows():
        lines.append(metric_table_row(row))
    return "\n".join(lines)


def markdown_hyper_table(hyper_rows: pd.DataFrame) -> str:
    lines = [
        "| Параметр | Значение | MAPE | ΔMAPE, п.п. | R² | ΔR² |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in hyper_rows.iterrows():
        lines.append(hyper_table_row(row))
    return "\n".join(lines)


def describe_feature_sensitivity(ablation: pd.DataFrame) -> tuple[str, str]:
    candidates = ablation[ablation["Удаленный признак/группа"] != "baseline"].copy()
    positive = candidates[candidates["ΔMAPE, п.п."] > 0].sort_values("ΔMAPE, п.п.", ascending=False)
    weak = candidates.reindex(candidates["ΔMAPE, п.п."].abs().sort_values().index).head(3)

    if positive.empty:
        strong_text = "В ablation analysis не найдено удаления признаков, которое заметно ухудшило MAPE."
    else:
        labels = [
            f"{row['Удаленный признак/группа']} (+{fmt_float(row['ΔMAPE, п.п.'], 2)} п.п.)"
            for _, row in positive.head(3).iterrows()
        ]
        strong_text = "Сильнее всего качество менялось при удалении: " + "; ".join(labels) + "."

    weak_labels = [
        f"{row['Удаленный признак/группа']} ({fmt_float(row['ΔMAPE, п.п.'], 2)} п.п.)"
        for _, row in weak.iterrows()
    ]
    weak_text = (
        "Минимальное изменение MAPE дали: "
        + "; ".join(weak_labels)
        + ". Это означает, что часть признаков в текущей конфигурации может иметь слабый вклад или частично дублироваться другими признаками."
    )
    return strong_text, weak_text


def describe_hyper_sensitivity(hyper: pd.DataFrame) -> str:
    non_baseline = hyper[hyper["ΔMAPE, п.п."].abs() > 1e-12].copy()
    if non_baseline.empty:
        return "В проверенной сетке изменение параметров не изменило MAPE относительно baseline."

    by_parameter = (
        non_baseline.assign(abs_delta=non_baseline["ΔMAPE, п.п."].abs())
        .sort_values("abs_delta", ascending=False)
        .groupby("Параметр", as_index=False)
        .first()
        .sort_values("abs_delta", ascending=False)
    )
    strongest = by_parameter.iloc[0]
    text = (
        f"Наиболее заметное изменение MAPE связано с параметром {strongest['Параметр']}="
        f"{format_parameter_value(strongest['Значение'])}: ΔMAPE {fmt_float(strongest['ΔMAPE, п.п.'], 2)} п.п., "
        f"ΔR² {fmt_r2(strongest['ΔR²'])}."
    )

    complexity_rows = hyper[
        ((hyper["Параметр"] == "depth") & (hyper["Значение"].astype(float) > 8))
        | ((hyper["Параметр"] == "iterations") & (hyper["Значение"].astype(float) > 800))
    ]
    worsened = complexity_rows[
        (complexity_rows["ΔMAPE, п.п."] > 0) | (complexity_rows["ΔR²"] < 0)
    ]
    if not worsened.empty:
        text += " При увеличении сложности модели часть конфигураций ухудшает MAPE или R², поэтому признаки переобучения нельзя исключать."
    else:
        text += " В проверенной сетке увеличение сложности не дало явного ухудшения по MAPE и R²."
    return text


def build_article(
    impact_rows: list[dict[str, str]],
    ablation: pd.DataFrame,
    hyper: pd.DataFrame,
    summary: dict[str, Any],
) -> str:
    feature_candidates = ablation[ablation["Удаленный признак/группа"] != "baseline"].copy()
    feature_top = feature_candidates.sort_values("ΔMAPE, п.п.", ascending=False).head(10)
    feature_strong, feature_weak = describe_feature_sensitivity(ablation)
    hyper_text = describe_hyper_sensitivity(hyper)

    impact_table = markdown_impact_table(impact_rows)
    feature_table = markdown_feature_table(feature_top)
    hyper_table = markdown_hyper_table(hyper)

    outliers = summary["outliers"]
    upper_1 = outliers["upper_1pct_removed"]
    upper_5 = outliers["upper_5pct_removed"]
    outlier_text = (
        f"После удаления верхнего 1% цен MAPE изменился на "
        f"{fmt_float(upper_1['delta_vs_baseline']['mape'], 2)} п.п.; "
        f"после удаления верхних 5% цен MAPE изменился на "
        f"{fmt_float(upper_5['delta_vs_baseline']['mape'], 2)} п.п."
    )

    split_description = (
        "фиксированном train/test split с test_size=0,2 и random_state=42"
        if summary["metadata"]["split_strategy"] == "fixed_train_test_split"
        else "5-fold cross-validation с random_state=42"
    )

    return f"""# Ограничения модели и анализ чувствительности

## 1. Матрица влияния ограничений на точность

Модель используется как proxy-valuation модель, так как обучение выполнялось на ценах объявлений, а не на данных фактических сделок. Поэтому часть ограничений можно оценить только косвенно через эксперименты с признаками, выбросами и качеством на подгруппах данных.

{impact_table}

Численные оценки в таблице относятся только к доступному датасету `{HF_DATASET_NAME}` и схеме проверки на {split_description}. Ограничения, связанные с отсутствием transaction prices и недостающими внешними признаками, не оценивались количественно, потому что в текущих данных нет прямого источника для такой проверки.

## 2. Анализ чувствительности к признакам

{feature_table}

{feature_strong} {feature_weak}

## 3. Анализ чувствительности к параметрам модели

{hyper_table}

{hyper_text} Небольшие изменения параметров следует интерпретировать вместе с разбросом 5-fold cross-validation, так как сама валидация показывает заметную вариативность между фолдами.

## 4. Готовый фрагмент для статьи

Для оценки ограничений модели был проведен набор дополнительных экспериментов. Часть ограничений можно проверить количественно на имеющемся датасете, однако ограничения, связанные с отсутствием данных фактических сделок и внешних характеристик объекта, требуют дополнительных источников данных.

Таблица 5 - Матрица влияния ограничений на точность

{impact_table}

Полученные результаты показывают, что не все ограничения можно выразить численно в рамках текущего датасета. Поэтому численные значения следует рассматривать как оценку чувствительности модели на данных объявлений, а не как прямое измерение ошибки рыночной оценки.

Анализ чувствительности к признакам показал, что качество модели сильнее всего зависит от признаков и групп, которые дают наибольший прирост MAPE при удалении. Если удаление отдельного признака почти не меняет MAPE или даже немного улучшает качество, это может означать слабый вклад признака, шум или дублирование информации другими признаками.

Анализ чувствительности к параметрам CatBoost показал, какие изменения конфигурации сильнее влияют на MAPE и R². {hyper_text}

Отдельно была проверена чувствительность к ценовым выбросам. {outlier_text} Это показывает, что оценку качества модели нужно интерпретировать с учетом структуры дорогих объектов в выборке.
"""


def run_limitations_impact(
    data_path: Path,
    feature_ablation_path: Path,
    hyperparameter_path: Path,
    n_splits: int,
    strategy: str,
    test_size: float,
    random_state: int,
    min_group_count: int,
    force_download: bool,
) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    if not feature_ablation_path.exists():
        raise FileNotFoundError(f"Feature ablation CSV not found: {feature_ablation_path}")
    if not hyperparameter_path.exists():
        raise FileNotFoundError(f"Hyperparameter sensitivity CSV not found: {hyperparameter_path}")

    raw_df = load_dataset_frame(data_path, force_download=force_download)
    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)
    raw_aligned = raw_df.loc[X.index].copy()
    if strategy == "holdout":
        y_eval, predictions, raw_eval, X_eval, baseline_metrics = validation_predictions(
            X=X,
            y=y,
            raw_aligned=raw_aligned,
            feature_config=feature_config,
            test_size=test_size,
            random_state=random_state,
        )
    else:
        baseline_metrics = evaluate_cv(X, y, feature_config, n_splits, random_state)
        predictions = out_of_fold_predictions(X, y, feature_config, n_splits, random_state)
        y_eval = y
        raw_eval = raw_aligned
        X_eval = X

    missing_count = X_eval.isna().sum(axis=1)
    q75 = float(missing_count.quantile(0.75))
    high_missing_mask = missing_count >= q75 if q75 > 0 else missing_count > 0
    complete_mask = missing_count == 0
    missing_summary = {
        "calculated": True,
        "missing_count_q75": q75,
        "complete": metrics_for_mask(y_eval, predictions, complete_mask, min_group_count),
        "high_missing": metrics_for_mask(y_eval, predictions, high_missing_mask, min_group_count),
    }

    ablation = pd.read_csv(feature_ablation_path)
    hyper = pd.read_csv(hyperparameter_path)

    summary: dict[str, Any] = {
        "metadata": {
            "model_name": "catboost_regressor",
            "dataset_name": HF_DATASET_NAME,
            "dataset_path": str(data_path),
            "dataset_sha256": dataset_fingerprint(data_path) if data_path.exists() else None,
            "target_column": feature_config.target_column,
            "target_transform": "log1p",
            "inverse_transform": "expm1",
            "split_strategy": "random_kfold" if strategy == "cv" else "fixed_train_test_split",
            "n_splits": n_splits,
            "test_size": test_size if strategy == "holdout" else None,
            "shuffle": True,
            "random_state": random_state,
            "rows_before_cleaning": qc_summary["rows_before_cleaning"],
            "rows_after_cleaning": qc_summary["rows_after_cleaning"],
            "reports_dir": str(DEFAULT_REPORTS_DIR),
        },
        "baseline_metrics": baseline_metrics,
        "feature_ablation_impact": best_ablation_impact(ablation),
        "drift": parsed_at_drift_summary(raw_aligned),
        "geography": district_metrics(raw_eval, y_eval, predictions, min_group_count),
        "outliers": outlier_sensitivity(
            raw_df,
            baseline_metrics,
            strategy,
            n_splits,
            test_size,
            random_state,
        ),
        "missing_data": missing_summary,
        "not_quantified": {
            "listing_vs_transaction_prices": (
                "В проекте нет данных фактических сделок, поэтому нельзя напрямую "
                "измерить смещение между listing price и transaction price."
            ),
            "repair_legal_infrastructure_features": (
                "В датасете нет структурированных признаков юридического статуса и "
                "инфраструктуры, а текстовые поля исключены из текущего training pipeline."
            ),
        },
    }
    impact_rows = make_impact_matrix(summary)
    article = build_article(impact_rows, ablation, hyper, summary)
    return impact_rows, summary, article


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
        json.dump(summary, file, ensure_ascii=False, indent=2)
    article_path.write_text(article, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Матрица ограничений и markdown для статьи.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_LOCAL_DATASET_PATH)
    parser.add_argument("--feature-ablation-path", type=Path, default=DEFAULT_FEATURE_ABLATION_PATH)
    parser.add_argument("--hyperparameter-path", type=Path, default=DEFAULT_HYPERPARAMETER_PATH)
    parser.add_argument("--impact-path", type=Path, default=DEFAULT_IMPACT_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--article-path", type=Path, default=DEFAULT_ARTICLE_PATH)
    parser.add_argument("--strategy", choices=["cv", "holdout"], default="cv")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--min-group-count", type=int, default=50)
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    impact_rows, summary, article = run_limitations_impact(
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
    save_outputs(
        impact_rows=impact_rows,
        summary=summary,
        article=article,
        impact_path=args.impact_path,
        summary_path=args.summary_path,
        article_path=args.article_path,
    )
    print(f"Saved impact matrix: {args.impact_path}")
    print(f"Saved summary: {args.summary_path}")
    print(f"Saved article: {args.article_path}")


if __name__ == "__main__":
    main()
