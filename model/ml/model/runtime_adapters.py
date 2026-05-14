from __future__ import annotations

from decimal import Decimal
from typing import Any

from model.ml.model.feature_schema import LISTING_TO_MODEL_FIELD_MAP
from model.ml.model.persistence import LoadedModelBundle
from model.ml.model.normalization import normalize_feature_record


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def build_listing_model_payload(
    row: dict[str, Any],
    bundle: LoadedModelBundle,
    *,
    listing_currency: str,
) -> dict[str, Any]:
    supported_features = set(bundle.feature_config.feature_columns)
    payload: dict[str, Any] = {
        "listing_id": row["listing_id"],
        "listing_price": _to_float(row["listing_price"]),
        "listing_currency": listing_currency,
    }

    for model_field, source_field in LISTING_TO_MODEL_FIELD_MAP.items():
        if model_field not in supported_features:
            continue
        raw_value = row.get(source_field)
        payload[model_field] = _to_float(raw_value) if isinstance(raw_value, Decimal) else raw_value

    return normalize_feature_record(payload, bundle.feature_config)
