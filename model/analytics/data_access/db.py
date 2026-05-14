from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from model.analytics.config import AnalyticsConfig
from model.shared.db.models import Listing, NormalizedListing, Valuation
from model.shared.db.session import create_db_engine


NORMALIZED_SOURCE_DESCRIPTION = (
    "normalized_listings.normalized_payload после apps.normalization.service.normalize_raw_listing"
)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _payload_value(payload: dict[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        value = payload.get(field_name)
        if value is not None and value != "":
            return value
    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("normalized_payload") or {}
    price = _first_present(
        _payload_value(payload, "price", "listing_price", "listing_price_rub", "price_usd"),
        row.get("listing_price"),
    )
    area = _first_present(_payload_value(payload, "area", "total_area_m2"), row.get("area"))
    kitchen_area = _first_present(
        _payload_value(payload, "kitchen_area", "kitchen_area_m2"),
        row.get("kitchen_area_m2"),
    )
    level = _first_present(_payload_value(payload, "level", "floor"), row.get("floor"))
    levels = _first_present(_payload_value(payload, "levels", "total_floors"), row.get("total_floors"))
    district = _clean_text(_first_present(_payload_value(payload, "district", "districts"), row.get("district")))
    region = _clean_text(_payload_value(payload, "region"))

    return {
        "normalized_id": row.get("normalized_id"),
        "source_object_id": row.get("source_object_id"),
        "raw_listing_id": row.get("raw_listing_id"),
        "listing_id": _first_present(row.get("listing_id"), _payload_value(payload, "listing_id")),
        "title": row.get("title"),
        "validation_status": row.get("validation_status"),
        "is_train_eligible": bool(row.get("is_train_eligible")),
        "validation_errors": row.get("validation_errors") or [],
        "validation_warnings": row.get("validation_warnings") or [],
        "city": _clean_text(_first_present(_payload_value(payload, "city"), row.get("city"))),
        "district": district,
        "region": region,
        "district_group": district or (f"region:{region}" if region else "Не указан"),
        "area": _to_float(area),
        "kitchen_area": _to_float(kitchen_area),
        "rooms": _to_int(_first_present(_payload_value(payload, "rooms"), row.get("rooms"))),
        "level": _to_int(level),
        "levels": _to_int(levels),
        "year_built": _to_int(_first_present(_payload_value(payload, "year_built"), row.get("year_built"))),
        "building_type": _clean_text(_payload_value(payload, "building_type")),
        "object_type": _clean_text(_payload_value(payload, "object_type")),
        "latitude": _to_float(_first_present(_payload_value(payload, "latitude", "geo_lat"), row.get("latitude"))),
        "longitude": _to_float(_first_present(_payload_value(payload, "longitude", "geo_lon"), row.get("longitude"))),
        "price": _to_float(price),
        "listing_price": _to_float(price),
        "listing_currency": _clean_text(
            _first_present(_payload_value(payload, "listing_currency"), row.get("listing_currency"), "RUB")
        ),
        "stored_predicted_price": _to_float(row.get("stored_predicted_price")),
        "stored_delta_abs": _to_float(row.get("stored_delta_abs")),
        "stored_delta_pct": _to_float(row.get("stored_delta_pct")),
        "stored_score": _to_float(row.get("stored_score")),
        "source_url": row.get("source_url"),
    }


def _normalized_statement(limit: int | None):
    statement = (
        select(
            NormalizedListing.id.label("normalized_id"),
            NormalizedListing.source_object_id.label("source_object_id"),
            NormalizedListing.raw_listing_id.label("raw_listing_id"),
            NormalizedListing.listing_id.label("listing_id"),
            NormalizedListing.normalized_payload.label("normalized_payload"),
            NormalizedListing.validation_status.label("validation_status"),
            NormalizedListing.validation_errors.label("validation_errors"),
            NormalizedListing.validation_warnings.label("validation_warnings"),
            NormalizedListing.is_train_eligible.label("is_train_eligible"),
            Listing.title.label("title"),
            Listing.city.label("city"),
            Listing.district.label("district"),
            Listing.area.label("area"),
            Listing.kitchen_area_m2.label("kitchen_area_m2"),
            Listing.rooms.label("rooms"),
            Listing.floor.label("floor"),
            Listing.total_floors.label("total_floors"),
            Listing.year_built.label("year_built"),
            Listing.latitude.label("latitude"),
            Listing.longitude.label("longitude"),
            Listing.listing_price.label("listing_price"),
            Listing.listing_currency.label("listing_currency"),
            Listing.source_url.label("source_url"),
            Valuation.predicted_price.label("stored_predicted_price"),
            Valuation.undervaluation_delta.label("stored_delta_abs"),
            Valuation.undervaluation_percent.label("stored_delta_pct"),
            Valuation.score.label("stored_score"),
        )
        .select_from(NormalizedListing)
        .outerjoin(Listing, Listing.id == NormalizedListing.listing_id)
        .outerjoin(Valuation, Valuation.listing_id == Listing.id)
        .where(NormalizedListing.validation_status == "accepted")
        .order_by(NormalizedListing.id.asc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return statement


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    numeric_columns = [
        "area",
        "kitchen_area",
        "rooms",
        "level",
        "levels",
        "year_built",
        "latitude",
        "longitude",
        "price",
        "listing_price",
        "stored_predicted_price",
        "stored_delta_abs",
        "stored_delta_pct",
        "stored_score",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["price_per_m2"] = np.where(
        (frame["price"].notna()) & (frame["area"].notna()) & (frame["area"] > 0),
        frame["price"] / frame["area"],
        np.nan,
    )
    frame["district_group"] = frame["district_group"].fillna("Не указан").astype(str)
    frame.attrs["source_description"] = NORMALIZED_SOURCE_DESCRIPTION
    return frame


def load_normalized_dataset(config: AnalyticsConfig) -> pd.DataFrame:
    engine = create_db_engine(config.database_url)
    rows: list[dict[str, Any]] = []
    try:
        with Session(engine) as session:
            result = session.execute(
                _normalized_statement(config.max_rows).execution_options(yield_per=5_000)
            ).mappings()
            for row in result:
                rows.append(_flatten_row(dict(row)))
    finally:
        engine.dispose()

    return _prepare_frame(pd.DataFrame(rows))
