from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from model.ml.model.category_normalization import normalize_categories_record
from model.ml.model.feature_schema import russia2021_feature_config
from model.ml.model.inference_validation import validate_inference_record
from model.ml.model.normalization import normalize_feature_record


@dataclass(slots=True)
class NormalizationResult:
    normalized_payload: dict[str, Any]
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_train_eligible: bool = False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(record: dict[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        value = record.get(field_name)
        if value is not None and value != "":
            return value
    return None


def _address_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "street": _first_present(record, "street"),
        "house": _first_present(record, "house"),
        "district": _first_present(record, "district", "districts"),
        "city": _first_present(record, "city"),
        "region": _first_present(record, "region"),
        "full_address": _first_present(record, "full_address", "address", "user_address"),
        "latitude": _to_float(_first_present(record, "latitude", "coordinates_lat", "geo_lat")),
        "longitude": _to_float(_first_present(record, "longitude", "coordinates_lng", "geo_lon")),
    }


def normalize_raw_listing(raw_listing: dict[str, Any]) -> NormalizationResult:
    feature_config = russia2021_feature_config()
    normalized = {
        "listing_id": _first_present(raw_listing, "listing_id", "inner_id", "id"),
        "listing_price": _to_float(_first_present(raw_listing, "listing_price", "price")),
        "listing_currency": "RUB",
        "rooms": _first_present(raw_listing, "rooms"),
        "area": _first_present(raw_listing, "area", "total_area", "total_area_m2"),
        "kitchen_area": _first_present(raw_listing, "kitchen_area", "kitchen_area_m2"),
        "level": _first_present(raw_listing, "level", "floor"),
        "levels": _first_present(raw_listing, "levels", "total_floors"),
        "building_type": _first_present(raw_listing, "building_type"),
        "object_type": _first_present(raw_listing, "object_type"),
        "region": _first_present(raw_listing, "region"),
        **_address_payload(raw_listing),
    }
    normalized = normalize_feature_record(normalized, feature_config)
    normalized, invalid_categories = normalize_categories_record(normalized)
    if invalid_categories:
        normalized["__invalid_category_fields__"] = invalid_categories

    validation = validate_inference_record(normalized, feature_config)
    status = "accepted" if validation.is_valid else "rejected"
    return NormalizationResult(
        normalized_payload=validation.normalized_features,
        status=status,
        errors=validation.errors,
        warnings=validation.warnings,
        is_train_eligible=validation.is_valid and normalized.get("listing_price") is not None,
    )
