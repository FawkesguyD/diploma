from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.apps.analytics_service.config import FORMULA_BASELINE_COEFFICIENTS
from model.ml.model.feature_schema import RUSSIA2021_MODEL_FEATURE_COLUMNS
from model.ml.model.persistence import inverse_transform_predictions, load_model_bundle


DEFAULT_TRAIN_POOL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "train_pool.csv"
DEFAULT_VALID_POOL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "russia2021_prepared" / "valid_pool.csv"
DEFAULT_LINEAR_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "linear_regression_baseline.joblib"
DEFAULT_CATBOOST_CANDIDATES = (
    PROJECT_ROOT / "ml" / "artifacts" / "best_model_russia2021.joblib",
    PROJECT_ROOT / "ml" / "artifacts" / "catboost_regressor.joblib",
    PROJECT_ROOT / "ml" / "artifacts" / "best_model.joblib",
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports"
DEFAULT_ARTICLE_PATH = PROJECT_ROOT / "ARTICLE_SYNTHETIC_RANKING_TABLE.md"

RANDOM_STATE = 42
BENCHMARK_SIZE = 1000
LINEAR_TRAIN_SAMPLE_SIZE = 250_000
TARGET_LOG_COLUMN = "target_log_price"
METHOD_LABELS = {
    "statistical": "Статистический метод",
    "heuristic": "Эвристический скоринг",
    "linear_regression": "Linear regression",
    "catboost": "CatBoost",
}
SYNTHETIC_GROUPS = (
    ("undervalued", 350, 0.10, 0.35),
    ("neutral", 400, -0.05, 0.10),
    ("overpriced", 250, -0.30, -0.05),
)
STAT_GROUPS = (
    ("region", "object_type", "building_type", "rooms"),
    ("region", "object_type", "rooms"),
    ("region", "rooms"),
    ("region",),
)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_pool(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Pool not found: {path}")
    return pd.read_csv(path, usecols=columns)


def _price_from_log_target(frame: pd.DataFrame) -> pd.Series:
    return np.exp(pd.to_numeric(frame[TARGET_LOG_COLUMN], errors="coerce"))


def build_synthetic_control(valid_pool: pd.DataFrame, random_state: int) -> pd.DataFrame:
    if len(valid_pool) < BENCHMARK_SIZE:
        raise ValueError(f"valid_pool has {len(valid_pool)} rows, need at least {BENCHMARK_SIZE}")

    rng = np.random.default_rng(random_state)
    control = valid_pool.sample(n=BENCHMARK_SIZE, random_state=random_state).reset_index(names="valid_row_index")
    control["listing_id"] = control["valid_row_index"].map(lambda value: f"russia2021_valid_{int(value):07d}")
    control["P_true"] = _price_from_log_target(control)

    group_labels: list[str] = []
    u_true_values: list[float] = []
    for group_name, count, low, high in SYNTHETIC_GROUPS:
        group_labels.extend([group_name] * count)
        u_true_values.extend(rng.uniform(low, high, size=count).tolist())

    order = rng.permutation(BENCHMARK_SIZE)
    control["synthetic_discount_group"] = np.asarray(group_labels, dtype=object)[order]
    control["U_true"] = np.asarray(u_true_values, dtype=float)[order]
    control["P_list_synthetic"] = control["P_true"] / (1.0 + control["U_true"])
    control["is_invest_attractive"] = (control["U_true"] >= 0.10).astype(int)

    output_columns = [
        "listing_id",
        "P_true",
        "P_list_synthetic",
        "U_true",
        "synthetic_discount_group",
        "is_invest_attractive",
        *RUSSIA2021_MODEL_FEATURE_COLUMNS,
    ]
    return control.loc[:, output_columns].copy()


def _train_price_per_m2_medians(train_pool: pd.DataFrame) -> dict[tuple[str, ...], pd.Series]:
    train = train_pool.copy()
    train["P_true"] = _price_from_log_target(train)
    train["price_per_m2"] = train["P_true"] / train["area"].replace({0: np.nan})
    train = train.replace([np.inf, -np.inf], np.nan).dropna(subset=["price_per_m2"])
    medians: dict[tuple[str, ...], pd.Series] = {}
    for group_columns in STAT_GROUPS:
        medians[group_columns] = train.groupby(list(group_columns), dropna=False)["price_per_m2"].median()
    medians[tuple()] = pd.Series({"__global__": float(train["price_per_m2"].median())})
    return medians


def _lookup_stat_median(row: pd.Series, medians: dict[tuple[str, ...], pd.Series]) -> float:
    for group_columns in STAT_GROUPS:
        key: Any
        if len(group_columns) == 1:
            key = row[group_columns[0]]
        else:
            key = tuple(row[column] for column in group_columns)
        group_medians = medians[group_columns]
        if key in group_medians.index:
            value = float(group_medians.loc[key])
            if np.isfinite(value):
                return value
    return float(medians[tuple()].loc["__global__"])


def predict_statistical(train_pool: pd.DataFrame, control: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    medians = _train_price_per_m2_medians(train_pool)
    median_values = control.apply(lambda row: _lookup_stat_median(row, medians), axis=1)
    predictions = median_values.to_numpy(dtype=float) * control["area"].to_numpy(dtype=float)
    return predictions, {
        "source": "train_pool median price per m2",
        "train_rows": int(len(train_pool)),
        "group_fallback_order": ["+".join(group) for group in STAT_GROUPS] + ["global"],
    }


def predict_heuristic(control: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    coefficients = FORMULA_BASELINE_COEFFICIENTS
    predictions = (
        coefficients["intercept"]
        + control["area"].astype(float) * coefficients["area"]
        + control["kitchen_area"].astype(float) * coefficients["kitchen_area"]
        + control["rooms"].astype(float) * coefficients["rooms"]
        + control["level"].astype(float) * coefficients["level"]
        + control["levels"].astype(float) * coefficients["levels"]
    )
    return predictions.clip(lower=0).to_numpy(dtype=float), {
        "source": "FORMULA_BASELINE_COEFFICIENTS",
        "coefficients": dict(coefficients),
    }


def _artifact_feature_columns(payload: dict[str, Any]) -> list[str]:
    feature_config = payload.get("feature_config", {})
    return list(feature_config.get("numerical_features", [])) + list(feature_config.get("categorical_features", []))


def _load_compatible_linear_artifact(path: Path) -> tuple[Any | None, dict[str, Any]]:
    if not path.exists():
        return None, {"artifact_path": str(path), "usable": False, "reason": "artifact missing"}
    payload = joblib.load(path)
    if not isinstance(payload, dict):
        return None, {"artifact_path": str(path), "usable": False, "reason": "unexpected payload type"}

    feature_columns = _artifact_feature_columns(payload)
    expected = list(RUSSIA2021_MODEL_FEATURE_COLUMNS)
    target_column = payload.get("target_column") or payload.get("feature_config", {}).get("target_column")
    base_currency = (payload.get("base_currency") or "").upper()
    compatible = feature_columns == expected and target_column == "price" and base_currency in {"", "RUB"}
    if not compatible:
        return None, {
            "artifact_path": str(path),
            "usable": False,
            "reason": "artifact schema is not compatible with Russia 2021 RUB holdout",
            "artifact_target_column": target_column,
            "artifact_base_currency": base_currency or None,
            "artifact_features": feature_columns,
            "benchmark_features": expected,
        }
    return payload, {"artifact_path": str(path), "usable": True, "reason": None}


def predict_linear_regression(
    train_pool: pd.DataFrame,
    control: pd.DataFrame,
    linear_model_path: Path,
    random_state: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    payload, metadata = _load_compatible_linear_artifact(linear_model_path)
    feature_columns = list(RUSSIA2021_MODEL_FEATURE_COLUMNS)
    if payload is not None:
        raw_predictions = payload["model"].predict(control.loc[:, feature_columns])
        predictions = np.expm1(raw_predictions) if bool(payload.get("log_target", True)) else raw_predictions
        metadata["source"] = "existing linear_regression_baseline.joblib"
        return np.clip(np.asarray(predictions, dtype=float), 0, None), metadata

    train_sample_size = min(LINEAR_TRAIN_SAMPLE_SIZE, len(train_pool))
    train_sample = train_pool.sample(n=train_sample_size, random_state=random_state)
    X_train = train_sample.loc[:, feature_columns].astype(float)
    y_train = train_sample[TARGET_LOG_COLUMN].astype(float)
    model = LinearRegression()
    model.fit(X_train, y_train)
    predictions = np.exp(model.predict(control.loc[:, feature_columns].astype(float)))
    metadata.update(
        {
            "source": "deterministic in-script LinearRegression fitted on train_pool log(price)",
            "train_rows": int(train_sample_size),
            "feature_columns": feature_columns,
        }
    )
    return np.clip(np.asarray(predictions, dtype=float), 0, None), metadata


def _resolve_catboost_model_path(candidates: tuple[Path, ...]) -> Path:
    for path in candidates:
        if not path.exists():
            continue
        try:
            bundle = load_model_bundle(path)
        except Exception:
            continue
        model_module = type(bundle.model).__module__.lower()
        model_name = str(bundle.model_name).lower()
        if "catboost" in model_module or "catboost" in model_name:
            if bundle.base_currency.upper() == "RUB" and bundle.target_column == "price":
                return path
    raise FileNotFoundError("No compatible RUB CatBoost artifact found.")


def predict_catboost(control: pd.DataFrame, candidates: tuple[Path, ...]) -> tuple[np.ndarray, dict[str, Any]]:
    model_path = _resolve_catboost_model_path(candidates)
    bundle = load_model_bundle(model_path)
    feature_columns = list(bundle.feature_config.feature_columns)
    frame = control.loc[:, feature_columns].copy()
    for column in bundle.feature_config.categorical_features:
        frame[column] = frame[column].fillna("missing").astype(str)
    raw_predictions = bundle.model.predict(frame)
    predictions = inverse_transform_predictions(raw_predictions, bundle.target_transform)
    return np.clip(np.asarray(predictions, dtype=float), 0, None), {
        "artifact_path": str(model_path),
        "model_name": bundle.model_name,
        "target_transform": bundle.target_transform,
        "base_currency": bundle.base_currency,
        "feature_columns": feature_columns,
    }


def _ndcg_at_k(relevance: pd.Series, score: pd.Series, k: int) -> float:
    values = pd.DataFrame({"relevance": relevance, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    values["relevance"] = values["relevance"].clip(lower=0)
    if values.empty or values["relevance"].sum() <= 0:
        return float("nan")
    k = min(k, len(values))
    ranked = values.sort_values("score", ascending=False).head(k)
    ideal = values.sort_values("relevance", ascending=False).head(k)
    discounts = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum((np.power(2, ranked["relevance"].to_numpy()) - 1.0) * discounts))
    idcg = float(np.sum((np.power(2, ideal["relevance"].to_numpy()) - 1.0) * discounts))
    return float("nan") if idcg == 0 else dcg / idcg


def _precision_at_k(labels: pd.Series, score: pd.Series, k: int) -> float:
    values = pd.DataFrame({"label": labels, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return float("nan")
    k = min(k, len(values))
    return float((values.sort_values("score", ascending=False).head(k)["label"] == 1).mean())


def _profit_capture_at_k(opportunity_value: pd.Series, score: pd.Series, k: int) -> float:
    values = pd.DataFrame({"value": opportunity_value, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    values["value"] = values["value"].clip(lower=0)
    if values.empty or values["value"].sum() <= 0:
        return float("nan")
    k = min(k, len(values))
    captured = float(values.sort_values("score", ascending=False).head(k)["value"].sum())
    ideal = float(values.sort_values("value", ascending=False).head(k)["value"].sum())
    return float("nan") if ideal == 0 else captured / ideal


def metrics_for_method(control: pd.DataFrame, method_id: str, predictions: np.ndarray) -> dict[str, Any]:
    p_true = control["P_true"].astype(float)
    p_list = control["P_list_synthetic"].astype(float)
    u_pred = (predictions - p_list) / p_list
    errors = predictions - p_true
    opportunity_value = (control["U_true"].clip(lower=0).astype(float) * p_list).rename("opportunity_value")
    return {
        "method_id": method_id,
        "Метод": METHOD_LABELS[method_id],
        "NDCG@10": _ndcg_at_k(control["U_true"], pd.Series(u_pred), 10),
        "NDCG@20": _ndcg_at_k(control["U_true"], pd.Series(u_pred), 20),
        "Precision@10": _precision_at_k(control["is_invest_attractive"], pd.Series(u_pred), 10),
        "ProfitCapture@10": _profit_capture_at_k(opportunity_value, pd.Series(u_pred), 10),
        "MAE": float(np.mean(np.abs(errors))),
        "MAPE": float(np.mean(np.abs(errors / p_true))),
    }


def _format_metric(value: float, digits: int = 3) -> str:
    if not np.isfinite(value):
        return "не рассчитано"
    return f"{value:.{digits}f}".replace(".", ",")


def _format_percent(value: float, digits: int = 1) -> str:
    if not np.isfinite(value):
        return "не рассчитано"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _format_money(value: float) -> str:
    if not np.isfinite(value):
        return "не рассчитано"
    return f"{int(round(value)):,}".replace(",", " ")


def _best_label(frame: pd.DataFrame, metric: str) -> tuple[str, float]:
    best_value = float(frame[metric].max())
    labels = frame[np.isclose(frame[metric], best_value)]["Метод"].astype(str).tolist()
    return ", ".join(labels), best_value


def _catboost_difference(frame: pd.DataFrame, metric: str) -> tuple[str, float, float]:
    catboost = frame[frame["method_id"] == "catboost"].iloc[0]
    baselines = frame[frame["method_id"] != "catboost"].copy()
    baselines["abs_delta"] = (baselines[metric] - float(catboost[metric])).abs()
    baseline = baselines.sort_values("abs_delta", ascending=True).iloc[0]
    return str(baseline["Метод"]), float(catboost[metric]), float(catboost[metric] - baseline[metric])


def build_article(frame: pd.DataFrame, metadata: dict[str, Any]) -> str:
    lines = [
        "# Таблица 4 - Детальное сравнение методов на synthetic proxy benchmark",
        "",
        "| Метод | NDCG@10 | NDCG@20 | Precision@10 | ProfitCapture@10 | MAE | MAPE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in frame.iterrows():
        cells = [
            str(row["Метод"]),
            _format_metric(float(row["NDCG@10"])),
            _format_metric(float(row["NDCG@20"])),
            _format_percent(float(row["Precision@10"])),
            _format_metric(float(row["ProfitCapture@10"])),
            _format_money(float(row["MAE"])),
            _format_percent(float(row["MAPE"]), digits=2),
        ]
        if row["method_id"] == "catboost":
            cells = [f"**{cell}**" for cell in cells]
        lines.append("| " + " | ".join(cells) + " |")

    ndcg_best = _best_label(frame, "NDCG@10")
    precision_best = _best_label(frame, "Precision@10")
    profit_best = _best_label(frame, "ProfitCapture@10")
    nearest_name, catboost_ndcg, ndcg_delta = _catboost_difference(frame, "NDCG@10")
    direction = "выше" if ndcg_delta > 0 else "ниже" if ndcg_delta < 0 else "на уровне"
    lines.extend(
        [
            "",
            "Краткая расшифровка:",
            f"- Лучший метод по NDCG@10: {ndcg_best[0]} ({_format_metric(ndcg_best[1])}).",
            f"- Лучший метод по Precision@10: {precision_best[0]} ({_format_percent(precision_best[1])}).",
            f"- Лучший метод по ProfitCapture@10: {profit_best[0]} ({_format_metric(profit_best[1])}).",
            (
                "- CatBoost по NDCG@10 имеет значение "
                f"{_format_metric(catboost_ndcg)}, что на {_format_metric(abs(ndcg_delta))} "
                f"{direction} ближайшего baseline ({nearest_name})."
            ),
            (
                "- Для инвестора это означает, что метод с лучшими ranking-метриками лучше "
                "ранжирует верхнюю часть списка объектов, где обычно ограничен бюджет проверки и due diligence."
            ),
            "",
            (
                "Данная проверка является synthetic proxy benchmark, так как в открытом датасете "
                "отсутствуют цены фактических сделок. Поэтому результаты показывают способность "
                "методов находить искусственно заданную недооцененность, но не являются прямой "
                "оценкой фактической инвестиционной доходности."
            ),
            "",
            "Методологические детали:",
            f"- Benchmark построен на {metadata['benchmark_rows']} объектах из holdout `valid_pool.csv`.",
            "- Статистический baseline рассчитывает медианы цены за м² только на `train_pool.csv`.",
            f"- Linear regression: {metadata['methods']['linear_regression']['source']}.",
            f"- CatBoost: `{metadata['methods']['catboost']['artifact_path']}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    control: pd.DataFrame,
    metrics_frame: pd.DataFrame,
    metadata: dict[str, Any],
    output_dir: Path,
    article_path: Path,
) -> None:
    _ensure_parent(output_dir / "synthetic_control_objects_1000.csv")
    control.to_csv(output_dir / "synthetic_control_objects_1000.csv", index=False)

    metrics_columns = ["Метод", "NDCG@10", "NDCG@20", "Precision@10", "ProfitCapture@10", "MAE", "MAPE"]
    metrics_frame.loc[:, metrics_columns].to_csv(
        output_dir / "synthetic_ranking_metrics_comparison.csv",
        index=False,
    )
    json_payload = {
        "metadata": metadata,
        "metrics": metrics_frame.loc[:, ["method_id", *metrics_columns]].to_dict(orient="records"),
    }
    with (output_dir / "synthetic_ranking_metrics_comparison.json").open("w", encoding="utf-8") as file:
        json.dump(json_payload, file, ensure_ascii=False, indent=2)

    _ensure_parent(article_path)
    article_path.write_text(build_article(metrics_frame, metadata), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    feature_columns = list(RUSSIA2021_MODEL_FEATURE_COLUMNS)
    pool_columns = [TARGET_LOG_COLUMN, *feature_columns]
    train_pool = _read_pool(args.train_pool, pool_columns)
    valid_pool = _read_pool(args.valid_pool, pool_columns)

    control = build_synthetic_control(valid_pool, args.random_state)
    method_predictions: dict[str, np.ndarray] = {}
    method_metadata: dict[str, Any] = {}

    method_predictions["statistical"], method_metadata["statistical"] = predict_statistical(train_pool, control)
    method_predictions["heuristic"], method_metadata["heuristic"] = predict_heuristic(control)
    method_predictions["linear_regression"], method_metadata["linear_regression"] = predict_linear_regression(
        train_pool,
        control,
        args.linear_model,
        args.random_state,
    )
    method_predictions["catboost"], method_metadata["catboost"] = predict_catboost(
        control,
        tuple(args.catboost_model),
    )

    metrics_frame = pd.DataFrame(
        [metrics_for_method(control, method_id, predictions) for method_id, predictions in method_predictions.items()]
    )
    group_counts = control["synthetic_discount_group"].value_counts().sort_index().to_dict()
    metadata = {
        "random_state": args.random_state,
        "train_pool": str(args.train_pool),
        "valid_pool": str(args.valid_pool),
        "benchmark_rows": int(len(control)),
        "group_counts": {str(key): int(value) for key, value in group_counts.items()},
        "label_rule": "is_invest_attractive = 1 if U_true >= 0.10 else 0",
        "price_formula": "P_list_synthetic = P_true / (1 + U_true)",
        "methods": method_metadata,
        "metric_definitions": {
            "U_pred": "(P_pred - P_list_synthetic) / P_list_synthetic",
            "NDCG": "relevance = max(U_true, 0)",
            "Precision@10": "share of is_invest_attractive in top 10 by U_pred",
            "ProfitCapture@10": "captured positive synthetic opportunity value in top 10 divided by ideal top 10",
            "MAE": "mean absolute error between P_pred and P_true",
            "MAPE": "mean absolute percentage error between P_pred and P_true",
        },
    }
    write_outputs(control, metrics_frame, metadata, args.output_dir, args.article_path)
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-pool", type=Path, default=DEFAULT_TRAIN_POOL_PATH)
    parser.add_argument("--valid-pool", type=Path, default=DEFAULT_VALID_POOL_PATH)
    parser.add_argument("--linear-model", type=Path, default=DEFAULT_LINEAR_MODEL_PATH)
    parser.add_argument("--catboost-model", type=Path, nargs="+", default=list(DEFAULT_CATBOOST_CANDIDATES))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--article-path", type=Path, default=DEFAULT_ARTICLE_PATH)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    return parser.parse_args()


def main() -> None:
    metadata = run(parse_args())
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
