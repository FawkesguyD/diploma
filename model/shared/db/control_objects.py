from __future__ import annotations

import os
from decimal import Decimal
from typing import Any


DEFAULT_CONTROL_OBJECT_SAMPLE_SEED = 42
CONTROL_OBJECT_SAMPLE_SEED_ENV = "CONTROL_OBJECT_SAMPLE_SEED"
ANALYTICS_CONTROL_SAMPLE_SEED_ENV = "ANALYTICS_CONTROL_SAMPLE_SEED"

SOURCE_PAYLOAD_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "address", "full_address"),
    "city": ("city",),
    "district": ("district", "districts"),
    "condition": ("condition",),
    "seller_type": ("seller_type", "user_type"),
    "year_built": ("year_built",),
}


def get_control_object_sample_seed() -> int:
    raw_value = os.getenv(CONTROL_OBJECT_SAMPLE_SEED_ENV) or os.getenv(ANALYTICS_CONTROL_SAMPLE_SEED_ENV)
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CONTROL_OBJECT_SAMPLE_SEED
    return int(raw_value)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def payload_value(payload: dict[str, Any] | None, *field_names: str) -> Any:
    if not payload:
        return None
    for field_name in field_names:
        value = payload.get(field_name)
        if value is not None and value != "":
            return value
    return None


def payload_text(payload: dict[str, Any] | None, field_name: str) -> str | None:
    return clean_text(payload_value(payload, *SOURCE_PAYLOAD_FIELD_ALIASES.get(field_name, (field_name,))))


def payload_int(payload: dict[str, Any] | None, field_name: str) -> int | None:
    value = payload_value(payload, *SOURCE_PAYLOAD_FIELD_ALIASES.get(field_name, (field_name,)))
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def control_object_listing_id(row: dict[str, Any]) -> int:
    listing_id = row.get("listing_id")
    if listing_id is None:
        listing_id = row["control_object_id"]
    return int(listing_id)


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: decimal_to_float(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimal_to_float(item) for item in value]
    return value


def listing_projection_from_control_row(row: dict[str, Any]) -> dict[str, Any]:
    source_payload = row.get("source_payload") or {}
    source_object_id = clean_text(row.get("source_object_id")) or str(control_object_listing_id(row))
    title = clean_text(row.get("title")) or payload_text(source_payload, "title") or f"Объект {source_object_id}"

    return {
        "id": control_object_listing_id(row),
        "title": title,
        "city": clean_text(row.get("city")) or payload_text(source_payload, "city"),
        "district": clean_text(row.get("district")) or payload_text(source_payload, "district") or clean_text(row.get("region")),
        "area": row.get("area"),
        "kitchen_area_m2": row.get("kitchen_area"),
        "rooms": row.get("rooms"),
        "floor": row.get("floor") if row.get("floor") is not None else row.get("level"),
        "total_floors": row.get("total_floors") if row.get("total_floors") is not None else row.get("levels"),
        "building_type": clean_text(row.get("building_type")),
        "condition": clean_text(row.get("condition")) or payload_text(source_payload, "condition"),
        "year_built": row.get("year_built") if row.get("year_built") is not None else payload_int(source_payload, "year_built"),
        "seller_type": clean_text(row.get("seller_type")) or payload_text(source_payload, "seller_type"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "listing_price": row.get("listing_price"),
        "listing_currency": clean_text(row.get("listing_currency")) or "RUB",
        "source_url": clean_text(row.get("source_url")),
    }
