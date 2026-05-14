from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


PRICE_PER_M2_COLUMN = "price_per_m2_rub"
DEFAULT_LOWER_QUANTILE = 0.05
DEFAULT_UPPER_QUANTILE = 0.95
MIN_SEGMENT_ROWS = 30


@dataclass(slots=True)
class MarketBoundResult:
    price_per_m2_raw: float
    price_per_m2_clamped: float
    clamped: bool
    lower_bound: float | None
    upper_bound: float | None
    segment_key: str | None


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _quantile_payload(values: pd.Series) -> dict[str, float | int]:
    clean_values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "count": int(len(clean_values)),
        "p05": float(clean_values.quantile(0.05)),
        "p10": float(clean_values.quantile(0.10)),
        "median": float(clean_values.quantile(0.50)),
        "p90": float(clean_values.quantile(0.90)),
        "p95": float(clean_values.quantile(0.95)),
    }


def _segment_key(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    parts: list[str] = []
    for field_name in fields:
        value = record.get(field_name)
        if value is None or pd.isna(value):
            return None
        parts.append(f"{field_name}={value}")
    return "|".join(parts)


def _candidate_segment_keys(record: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for fields in (
        ("region", "object_type", "building_type"),
        ("region", "object_type"),
        ("region", "building_type"),
        ("object_type", "building_type"),
        ("region",),
        ("object_type",),
        ("building_type",),
    ):
        key = _segment_key(record, fields)
        if key is not None:
            candidates.append(key)
    return candidates


def compute_market_bounds(
    frame: pd.DataFrame,
    *,
    price_column: str,
    area_column: str = "area",
    min_segment_rows: int = MIN_SEGMENT_ROWS,
) -> dict[str, Any]:
    working = frame.copy()
    price = pd.to_numeric(working[price_column], errors="coerce")
    area = pd.to_numeric(working[area_column], errors="coerce").replace({0: np.nan})
    working[PRICE_PER_M2_COLUMN] = (price / area).replace([np.inf, -np.inf], np.nan)
    working = working.dropna(subset=[PRICE_PER_M2_COLUMN])

    payload: dict[str, Any] = {
        "schema_version": 1,
        "unit": "RUB_PER_M2",
        "lower_quantile": DEFAULT_LOWER_QUANTILE,
        "upper_quantile": DEFAULT_UPPER_QUANTILE,
        "global": _quantile_payload(working[PRICE_PER_M2_COLUMN]) if not working.empty else {},
        "segments": {},
    }

    segment_fields = [
        ["region"],
        ["object_type"],
        ["building_type"],
        ["region", "object_type"],
        ["region", "building_type"],
        ["object_type", "building_type"],
        ["region", "object_type", "building_type"],
    ]
    for fields in segment_fields:
        if not set(fields).issubset(working.columns):
            continue
        for values, group in working.groupby(fields, dropna=True):
            if len(group) < min_segment_rows:
                continue
            if not isinstance(values, tuple):
                values = (values,)
            key = "|".join(f"{field}={value}" for field, value in zip(fields, values, strict=True))
            payload["segments"][key] = _quantile_payload(group[PRICE_PER_M2_COLUMN])

    return payload


def apply_market_bounds(
    *,
    price_per_m2: float,
    object_features: dict[str, Any],
    market_bounds: dict[str, Any] | None,
) -> MarketBoundResult:
    if not market_bounds:
        return MarketBoundResult(
            price_per_m2_raw=float(price_per_m2),
            price_per_m2_clamped=float(price_per_m2),
            clamped=False,
            lower_bound=None,
            upper_bound=None,
            segment_key=None,
        )

    bounds = None
    segment_key = None
    segments = market_bounds.get("segments") or {}
    for candidate_key in _candidate_segment_keys(object_features):
        candidate_bounds = segments.get(candidate_key)
        if candidate_bounds:
            bounds = candidate_bounds
            segment_key = candidate_key
            break

    if bounds is None:
        bounds = market_bounds.get("global") or {}
        segment_key = "global" if bounds else None

    lower_bound = _finite_float(bounds.get("p05"))
    upper_bound = _finite_float(bounds.get("p95"))
    if lower_bound is None or upper_bound is None or lower_bound <= 0 or upper_bound <= lower_bound:
        return MarketBoundResult(
            price_per_m2_raw=float(price_per_m2),
            price_per_m2_clamped=float(price_per_m2),
            clamped=False,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            segment_key=segment_key,
        )

    clamped_value = float(np.clip(price_per_m2, lower_bound, upper_bound))
    return MarketBoundResult(
        price_per_m2_raw=float(price_per_m2),
        price_per_m2_clamped=clamped_value,
        clamped=not np.isclose(clamped_value, price_per_m2),
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        segment_key=segment_key,
    )
