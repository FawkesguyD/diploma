from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from model.apps.analytics_service.config import FORMULA_BASELINE_COEFFICIENTS, FORMULA_BASELINE_NOTE
from model.analytics.charts.model_quality import load_inference_bundle
from model.analytics.config import AnalyticsConfig
from model.ml.model.inference import predict_proxy_valuation_from_bundle


PRICE_PER_METER_MIN_SEGMENT_ROWS = 5
RANKING_K_VALUES = (10, 20, 50, 100)
REQUESTED_MY_MODEL_METRICS = (
    "mae",
    "mape",
    "spearman_proxy_discount",
    "ndcg@10",
    "ndcg@20",
    "precision@10",
    "profit_capture@10",
)


FORMULA_COEFFICIENTS = dict(FORMULA_BASELINE_COEFFICIENTS)
FORMULA_LIMITATION = (
    f"{FORMULA_BASELINE_NOTE} Коэффициенты переиспользуются из apps.analytics_service.config; "
    "это эвристика, а не обученная модель."
)
PRICE_PER_METER_LIMITATION = (
    "Price per meter approach хранит исходный score listing_price / area. "
    "Для valuation estimate используется медианная цена за м² сегмента контрольной выборки без текущего объекта."
)

PRICE_PER_METER_GROUPS = (
    ("region", "object_type", "building_type", "rooms"),
    ("region", "object_type", "rooms"),
    ("region", "rooms"),
    ("region",),
    tuple(),
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _number(value: Any, default: float = 0.0) -> float:
    if _is_missing(value):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(number):
        return default
    return number


def _optional_number(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _safe_delta(estimate: pd.Series, listing_price: pd.Series) -> tuple[pd.Series, pd.Series]:
    estimate = pd.to_numeric(estimate, errors="coerce")
    listing_price = pd.to_numeric(listing_price, errors="coerce")
    delta_abs = estimate - listing_price
    delta_pct = delta_abs / listing_price.replace({0: np.nan})
    return delta_abs.replace([np.inf, -np.inf], np.nan), delta_pct.replace([np.inf, -np.inf], np.nan)


def _segment_mask(frame: pd.DataFrame, row: pd.Series, group_columns: tuple[str, ...]) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column in group_columns:
        value = row.get(column)
        if _is_missing(value):
            mask &= frame[column].isna()
        else:
            mask &= frame[column] == value
    return mask


def _segment_price_per_m2(
    frame: pd.DataFrame,
    row_index: int,
    *,
    min_segment_rows: int = PRICE_PER_METER_MIN_SEGMENT_ROWS,
) -> tuple[float | None, str | None, int]:
    row = frame.loc[row_index]
    for group_columns in PRICE_PER_METER_GROUPS:
        mask = _segment_mask(frame, row, group_columns)
        mask &= frame.index != row_index
        values = frame.loc[mask, "price_per_meter_score"].dropna()
        if not group_columns or len(values) >= min_segment_rows:
            if values.empty:
                return None, None, 0
            label = "global" if not group_columns else "+".join(group_columns)
            return float(values.median()), label, int(len(values))
    return None, None, 0


def add_price_per_meter_approach(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    listing_price = pd.to_numeric(result["listing_price"], errors="coerce")
    area = pd.to_numeric(result["area"], errors="coerce")
    result["price_per_meter_score"] = (listing_price / area.replace({0: np.nan})).replace(
        [np.inf, -np.inf],
        np.nan,
    )

    baselines: list[float | None] = []
    labels: list[str | None] = []
    counts: list[int] = []
    for row_index in result.index:
        baseline, label, count = _segment_price_per_m2(result, int(row_index))
        baselines.append(baseline)
        labels.append(label)
        counts.append(count)

    result["price_per_meter_baseline_m2"] = baselines
    result["price_per_meter_segment"] = labels
    result["price_per_meter_segment_rows"] = counts
    result["price_per_meter_estimate"] = result["price_per_meter_baseline_m2"] * area
    delta_abs, delta_pct = _safe_delta(result["price_per_meter_estimate"], listing_price)
    result["price_per_meter_delta_abs"] = delta_abs
    result["price_per_meter_delta_pct"] = delta_pct
    result["price_per_meter_ranking_signal"] = delta_pct
    return result


def formula_estimate(row: pd.Series, coefficients: dict[str, float] = FORMULA_COEFFICIENTS) -> float:
    estimate = coefficients["intercept"]
    for field_name in ("area", "kitchen_area", "rooms", "level", "levels"):
        value = _optional_number(row.get(field_name))
        if value is None:
            continue
        estimate += value * coefficients[field_name]
    return float(max(0.0, estimate))


def add_formula_approach(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    listing_price = pd.to_numeric(result["listing_price"], errors="coerce")
    result["formula_estimate"] = result.apply(formula_estimate, axis=1)
    delta_abs, delta_pct = _safe_delta(result["formula_estimate"], listing_price)
    result["formula_delta_abs"] = delta_abs
    result["formula_delta_pct"] = delta_pct
    result["formula_ranking_signal"] = delta_pct
    return result


def row_to_inference_payload(row: pd.Series) -> dict[str, Any]:
    payload = {
        "listing_id": row.get("listing_id"),
        "listing_price": row.get("listing_price"),
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
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }
    return {key: value for key, value in payload.items() if not _is_missing(value)}


def add_regression_approach(frame: pd.DataFrame, config: AnalyticsConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    result = frame.copy()
    listing_price = pd.to_numeric(result["listing_price"], errors="coerce")
    estimates: list[float | None] = []
    errors: list[str | None] = []
    metadata: dict[str, Any] = {"model_source": None, "load_error": None}

    try:
        bundle, model_source = load_inference_bundle(config)
        metadata["model_source"] = model_source
    except Exception as exc:
        metadata["load_error"] = str(exc)
        result["regression_estimate"] = np.nan
        result["regression_error"] = str(exc)
        result["regression_delta_abs"] = np.nan
        result["regression_delta_pct"] = np.nan
        result["regression_ranking_signal"] = np.nan
        return result, metadata

    for _, row in result.iterrows():
        try:
            response = predict_proxy_valuation_from_bundle(
                row_to_inference_payload(row),
                bundle,
                output_currency="RUB",
                include_explanation=False,
            )
            estimates.append(float(response["predicted_price_rub"]))
            errors.append(None)
        except Exception as exc:
            estimates.append(None)
            errors.append(str(exc))

    result["regression_estimate"] = estimates
    result["regression_error"] = errors
    delta_abs, delta_pct = _safe_delta(result["regression_estimate"], listing_price)
    result["regression_delta_abs"] = delta_abs
    result["regression_delta_pct"] = delta_pct
    result["regression_ranking_signal"] = delta_pct
    metadata["rows_failed"] = int(pd.Series(errors).notna().sum())
    return result, metadata


def add_my_model_alias(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["my_model_estimate"] = result["regression_estimate"]
    result["my_model_delta_abs"] = result["regression_delta_abs"]
    result["my_model_delta_pct"] = result["regression_delta_pct"]
    result["my_model_ranking_signal"] = result["regression_ranking_signal"]
    result["my_model_error"] = result["regression_error"]
    return result


def add_proxy_target_signals(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    price_per_m2 = pd.to_numeric(result["price_per_meter_score"], errors="coerce")
    baseline = pd.to_numeric(result["price_per_meter_baseline_m2"], errors="coerce")
    listing_price = pd.to_numeric(result["listing_price"], errors="coerce")
    result["target_proxy_price"] = pd.to_numeric(
        result.get("target_proxy_price", listing_price),
        errors="coerce",
    ).combine_first(listing_price)
    result["target_proxy_basis"] = "listing_price_proxy"
    result["target_proxy_discount_signal"] = ((baseline - price_per_m2) / price_per_m2.replace({0: np.nan})).replace(
        [np.inf, -np.inf],
        np.nan,
    )
    result["target_proxy_opportunity_value"] = (
        result["target_proxy_discount_signal"].clip(lower=0) * listing_price
    )
    return result


def build_comparison_frame(control_frame: pd.DataFrame, config: AnalyticsConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    result = control_frame.reset_index(drop=True).copy()
    result = add_price_per_meter_approach(result)
    result = add_formula_approach(result)
    result, regression_metadata = add_regression_approach(result, config)
    result = add_my_model_alias(result)
    result = add_proxy_target_signals(result)
    return result, regression_metadata


def value_metrics_for_method(
    frame: pd.DataFrame,
    *,
    method: str,
    estimate_column: str,
    target_column: str = "target_proxy_price",
) -> dict[str, Any]:
    values = frame[[target_column, estimate_column]].apply(pd.to_numeric, errors="coerce")
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    values = values[values[target_column] > 0]
    if values.empty:
        return {
            "method": method,
            "metric_layer": "value",
            "rows": 0,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r2": None,
        }

    y_true = values[target_column].to_numpy(dtype=float)
    y_pred = values[estimate_column].to_numpy(dtype=float)
    errors = y_pred - y_true
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    mape = float(np.mean(np.abs(errors / y_true)))
    denominator = float(np.sum(np.square(y_true - np.mean(y_true))))
    r2 = None if len(y_true) < 2 or denominator == 0 else float(1 - np.sum(np.square(errors)) / denominator)
    return {
        "method": method,
        "metric_layer": "value",
        "rows": int(len(values)),
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "r2": r2,
    }


def _spearman(left: pd.Series, right: pd.Series) -> float | None:
    pair = pd.concat(
        [
            pd.to_numeric(left, errors="coerce"),
            pd.to_numeric(right, errors="coerce"),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pair) < 3:
        return None
    return float(pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman"))


def _ndcg_at_k(relevance: pd.Series, score: pd.Series, k: int) -> float | None:
    values = pd.DataFrame({"relevance": relevance, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    values["relevance"] = values["relevance"].clip(lower=0)
    if values["relevance"].sum() <= 0:
        return None
    k = min(k, len(values))
    ranked = values.sort_values("score", ascending=False).head(k)
    ideal = values.sort_values("relevance", ascending=False).head(k)
    discounts = 1 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum((np.power(2, ranked["relevance"].to_numpy()) - 1) * discounts))
    idcg = float(np.sum((np.power(2, ideal["relevance"].to_numpy()) - 1) * discounts))
    return None if idcg == 0 else dcg / idcg


def _precision_at_k(relevance: pd.Series, score: pd.Series, k: int) -> float | None:
    values = pd.DataFrame({"relevance": relevance, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    relevant = values["relevance"] > 0
    if not bool(relevant.any()):
        return None
    k = min(k, len(values))
    top = values.sort_values("score", ascending=False).head(k)
    return float((top["relevance"] > 0).mean())


def _profit_capture_at_k(opportunity_value: pd.Series, score: pd.Series, k: int) -> float | None:
    values = pd.DataFrame({"value": opportunity_value, "score": score}).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    values["value"] = values["value"].clip(lower=0)
    if values["value"].sum() <= 0:
        return None
    k = min(k, len(values))
    captured = float(values.sort_values("score", ascending=False).head(k)["value"].sum())
    ideal = float(values.sort_values("value", ascending=False).head(k)["value"].sum())
    return None if ideal == 0 else captured / ideal


def ranking_metrics_for_method(
    frame: pd.DataFrame,
    *,
    method: str,
    signal_column: str,
) -> list[dict[str, Any]]:
    target_signal = pd.to_numeric(frame["target_proxy_discount_signal"], errors="coerce")
    opportunity_value = pd.to_numeric(frame["target_proxy_opportunity_value"], errors="coerce")
    signal = pd.to_numeric(frame[signal_column], errors="coerce")
    rows: list[dict[str, Any]] = [
        {
            "method": method,
            "metric_layer": "ranking",
            "metric": "spearman_proxy_discount",
            "k": None,
            "value": _spearman(signal, target_signal),
        }
    ]
    for k in RANKING_K_VALUES:
        rows.extend(
            [
                {
                    "method": method,
                    "metric_layer": "ranking",
                    "metric": "ndcg",
                    "k": k,
                    "value": _ndcg_at_k(target_signal, signal, k),
                },
                {
                    "method": method,
                    "metric_layer": "ranking",
                    "metric": "precision",
                    "k": k,
                    "value": _precision_at_k(target_signal, signal, k),
                },
                {
                    "method": method,
                    "metric_layer": "ranking",
                    "metric": "profit_capture",
                    "k": k,
                    "value": _profit_capture_at_k(opportunity_value, signal, k),
                },
            ]
        )
    return rows


def build_metrics_frame(comparison_frame: pd.DataFrame) -> pd.DataFrame:
    value_rows = [
        value_metrics_for_method(
            comparison_frame,
            method="price_per_meter",
            estimate_column="price_per_meter_estimate",
        ),
        value_metrics_for_method(
            comparison_frame,
            method="formula",
            estimate_column="formula_estimate",
        ),
        value_metrics_for_method(
            comparison_frame,
            method="regression",
            estimate_column="regression_estimate",
        ),
        value_metrics_for_method(
            comparison_frame,
            method="my_model",
            estimate_column="my_model_estimate",
        ),
    ]
    ranking_rows: list[dict[str, Any]] = []
    ranking_rows.extend(
        ranking_metrics_for_method(
            comparison_frame,
            method="price_per_meter",
            signal_column="price_per_meter_ranking_signal",
        )
    )
    ranking_rows.extend(
        ranking_metrics_for_method(
            comparison_frame,
            method="formula",
            signal_column="formula_ranking_signal",
        )
    )
    ranking_rows.extend(
        ranking_metrics_for_method(
            comparison_frame,
            method="regression",
            signal_column="regression_ranking_signal",
        )
    )
    ranking_rows.extend(
        ranking_metrics_for_method(
            comparison_frame,
            method="my_model",
            signal_column="my_model_ranking_signal",
        )
    )
    return pd.DataFrame(value_rows + ranking_rows)


def build_my_model_metrics_frame(metrics_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    value_metrics = metrics_frame[
        (metrics_frame["method"] == "my_model") & (metrics_frame["metric_layer"] == "value")
    ]
    if not value_metrics.empty:
        value_row = value_metrics.iloc[0]
        rows.extend(
            [
                {"method": "my_model", "metric": "MAE", "k": None, "value": value_row.get("mae")},
                {"method": "my_model", "metric": "MAPE", "k": None, "value": value_row.get("mape")},
            ]
        )

    ranking_metrics = metrics_frame[
        (metrics_frame["method"] == "my_model") & (metrics_frame["metric_layer"] == "ranking")
    ]
    metric_specs = [
        ("spearman_proxy_discount", None, "Spearman rank correlation"),
        ("ndcg", 10, "NDCG@10"),
        ("ndcg", 20, "NDCG@20"),
        ("precision", 10, "Precision@10"),
        ("profit_capture", 10, "ProfitCapture@10"),
    ]
    for metric_name, k_value, label in metric_specs:
        subset = ranking_metrics[ranking_metrics["metric"] == metric_name]
        if k_value is not None:
            subset = subset[subset["k"] == k_value]
        rows.append(
            {
                "method": "my_model",
                "metric": label,
                "k": k_value,
                "value": None if subset.empty else subset.iloc[0].get("value"),
            }
        )
    return pd.DataFrame(rows)


def build_ranking_comparison_frame(comparison_frame: pd.DataFrame) -> pd.DataFrame:
    result = comparison_frame[
        [
            "source_object_id",
            "listing_id",
            "listing_price",
            "area",
            "target_proxy_discount_signal",
            "target_proxy_opportunity_value",
            "price_per_meter_ranking_signal",
            "formula_ranking_signal",
            "regression_ranking_signal",
            "my_model_ranking_signal",
        ]
    ].copy()
    rank_columns = {
        "target_proxy_discount_signal": "target_proxy_rank",
        "price_per_meter_ranking_signal": "price_per_meter_rank",
        "formula_ranking_signal": "formula_rank",
        "regression_ranking_signal": "regression_rank",
        "my_model_ranking_signal": "my_model_rank",
    }
    for signal_column, rank_column in rank_columns.items():
        result[rank_column] = pd.to_numeric(result[signal_column], errors="coerce").rank(
            ascending=False,
            method="min",
            na_option="bottom",
        )
    return result.sort_values("target_proxy_rank", ascending=True, na_position="last")
