from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import islice
from pathlib import Path
from typing import Any, Iterator
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from model.apps.normalization.service import normalize_raw_listing
from model.shared.db.control_objects import decimal_to_float, get_control_object_sample_seed
from model.shared.db.models import AnalyticsControlObject, Listing, NormalizedListing
from model.shared.db.session import SessionLocal


LOGGER = logging.getLogger("services.data_migrator.importer")
DEFAULT_CSV_PATH = Path("./office-sale.csv")
FLOOR_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
ROOMS_PATTERN = re.compile(r"(\d+)\s*[- ]?(?:комн|rooms?)", re.IGNORECASE)
BATCH_SIZE = 500


@dataclass(slots=True)
class ImportStats:
    processed: int = 0
    imported: int = 0
    skipped: int = 0


def resolve_csv_path(csv_path: str | Path | None = None) -> Path:
    configured_path = csv_path or os.getenv("CSV_SOURCE_PATH") or DEFAULT_CSV_PATH
    return Path(configured_path)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.replace("\xa0", " ").strip()
    return normalized or None


def _parse_decimal(value: str | None) -> Decimal | None:
    normalized = _clean_text(value)
    if normalized is None:
        return None

    normalized = normalized.replace(" ", "").replace(",", ".")
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if not normalized:
        return None

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _convert_decimals_to_float(obj: Any) -> Any:
    return decimal_to_float(obj)


def _parse_int(value: str | None) -> int | None:
    normalized = _clean_text(value)
    if normalized is None:
        return None

    digits_only = re.sub(r"[^\d\-]", "", normalized)
    if not digits_only:
        return None

    try:
        return int(digits_only)
    except ValueError:
        return None


def _extract_total_floors(*candidates: str | None) -> int | None:
    for candidate in candidates:
        normalized = _clean_text(candidate)
        if normalized is None:
            continue

        match = FLOOR_PATTERN.search(normalized)
        if match:
            return int(match.group(2))

    return None


def _extract_rooms(title: str | None, description: str | None) -> int | None:
    for candidate in (title, description):
        normalized = _clean_text(candidate)
        if normalized is None:
            continue

        match = ROOMS_PATTERN.search(normalized)
        if match:
            return int(match.group(1))

    return None


def _extract_city(row: dict[str, str]) -> str | None:
    for field_name in ("address", "user_address"):
        value = _clean_text(row.get(field_name))
        if value is not None:
            return value.split(",")[0].strip()
    return None


def _count_images(value: str | None) -> int | None:
    normalized = _clean_text(value)
    if normalized is None:
        return None

    items = [item.strip() for item in normalized.split(",") if item.strip()]
    return len(items) or None


def _map_row_to_listing(row: dict[str, str]) -> dict[str, object] | None:
    listing_id = _parse_int(row.get("inner_id"))
    title = _clean_text(row.get("title"))

    if listing_id is None or title is None:
        return None

    return {
        "id": listing_id,
        "title": title,
        "city": _extract_city(row),
        "district": _clean_text(row.get("districts")),
        "area": _parse_decimal(row.get("total_area")),
        "rooms": _extract_rooms(row.get("title"), row.get("description")),
        "floor": _parse_int(row.get("floor")),
        "total_floors": _extract_total_floors(
            row.get("title"),
            row.get("formatted_full_info"),
            row.get("formatted_short_info"),
        ),
        "building_type": _clean_text(row.get("building_type")),
        "seller_type": _clean_text(row.get("user_type")),
        "latitude": _parse_decimal(row.get("coordinates_lat")),
        "longitude": _parse_decimal(row.get("coordinates_lng")),
        "photo_count": _count_images(row.get("images")),
        "listing_price": _parse_decimal(row.get("price")),
        "listing_currency": "RUB",
        "source_url": _clean_text(row.get("url")),
    }


def _batched(items: list[dict[str, object]], batch_size: int) -> Iterator[list[dict[str, object]]]:
    iterator = iter(items)
    while batch := list(islice(iterator, batch_size)):
        yield batch


def import_listings(csv_path: str | Path | None = None) -> ImportStats:
    resolved_path = resolve_csv_path(csv_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"CSV source not found: {resolved_path}")

    LOGGER.info("csv_read_start csv_path=%s", resolved_path)
    stats = ImportStats()
    rows_to_import: list[dict[str, object]] = []
    control_rows_to_import: list[dict[str, object]] = []
    normalized_rows_to_import: list[dict[str, object]] = []
    sample_seed = get_control_object_sample_seed()

    with resolved_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            stats.processed += 1
            mapped_row = _map_row_to_listing(row)

            if mapped_row is None:
                stats.skipped += 1
                continue
            if mapped_row.get("area") is None or mapped_row.get("listing_price") is None:
                stats.skipped += 1
                continue

            external_id = str(mapped_row["id"])
            source_object_id = f"office-sale.csv:{external_id}"
            normalization = normalize_raw_listing({**row, **mapped_row})
            source_payload = _convert_decimals_to_float(
                {
                    **row,
                    "listing_id": mapped_row["id"],
                    "title": mapped_row["title"],
                    "city": mapped_row.get("city"),
                    "district": mapped_row.get("district"),
                    "seller_type": mapped_row.get("seller_type"),
                }
            )
            control_rows_to_import.append(
                {
                    "source_object_id": source_object_id,
                    "listing_id": mapped_row["id"],
                    "listing_price": mapped_row["listing_price"],
                    "listing_currency": mapped_row["listing_currency"],
                    "target_proxy_price": mapped_row["listing_price"],
                    "target_source": "listing_price_proxy",
                    "area": mapped_row["area"],
                    "rooms": mapped_row.get("rooms"),
                    "kitchen_area": mapped_row.get("kitchen_area_m2"),
                    "level": mapped_row.get("floor"),
                    "levels": mapped_row.get("total_floors"),
                    "building_type": mapped_row.get("building_type"),
                    "object_type": _clean_text(row.get("object_type")),
                    "region": _clean_text(row.get("region")) or mapped_row.get("city"),
                    "latitude": mapped_row.get("latitude"),
                    "longitude": mapped_row.get("longitude"),
                    "source_url": mapped_row.get("source_url"),
                    "source_payload": source_payload,
                    "sample_seed": sample_seed,
                    "sample_rank": len(control_rows_to_import) + 1,
                }
            )
            normalized_rows_to_import.append(
                {
                    "source_object_id": source_object_id,
                    "listing_id": mapped_row["id"],
                    "normalized_payload": normalization.normalized_payload,
                    "validation_status": normalization.status,
                    "validation_errors": normalization.errors,
                    "validation_warnings": normalization.warnings,
                    "is_train_eligible": normalization.is_train_eligible,
                }
            )
            rows_to_import.append(mapped_row)

    if not rows_to_import:
        LOGGER.warning("csv_no_rows_to_import csv_path=%s", resolved_path)
        return stats

    updatable_columns = (
        "title",
        "city",
        "district",
        "area",
        "rooms",
        "floor",
        "total_floors",
        "building_type",
        "seller_type",
        "latitude",
        "longitude",
        "photo_count",
        "listing_price",
        "listing_currency",
        "source_url",
    )

    with SessionLocal() as session:
        try:
            for control_batch in _batched(control_rows_to_import, BATCH_SIZE):
                statement = insert(AnalyticsControlObject).values(control_batch)
                updatable_control_columns = (
                    "listing_id",
                    "listing_price",
                    "listing_currency",
                    "target_proxy_price",
                    "target_source",
                    "area",
                    "rooms",
                    "kitchen_area",
                    "level",
                    "levels",
                    "building_type",
                    "object_type",
                    "region",
                    "latitude",
                    "longitude",
                    "source_url",
                    "source_payload",
                    "sample_rank",
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[AnalyticsControlObject.sample_seed, AnalyticsControlObject.source_object_id],
                    set_={
                        **{
                            column_name: getattr(statement.excluded, column_name)
                            for column_name in updatable_control_columns
                        },
                        "updated_at": statement.excluded.updated_at,
                    },
                )
                session.execute(statement)

            for batch in _batched(rows_to_import, BATCH_SIZE):
                statement = insert(Listing).values(batch)
                update_mapping = {
                    column_name: getattr(statement.excluded, column_name)
                    for column_name in updatable_columns
                }
                statement = statement.on_conflict_do_update(
                    index_elements=[Listing.id],
                    set_=update_mapping,
                )
                session.execute(statement)
                stats.imported += len(batch)

            normalized_db_rows = []
            for row in normalized_rows_to_import:
                normalized_db_rows.append(
                    {
                        "source_object_id": row["source_object_id"],
                        "listing_id": row["listing_id"],
                        "normalized_payload": _convert_decimals_to_float(row["normalized_payload"]),
                        "validation_status": row["validation_status"],
                        "validation_errors": row["validation_errors"],
                        "validation_warnings": row["validation_warnings"],
                        "is_train_eligible": row["is_train_eligible"],
                    }
                )

            for normalized_batch in _batched(normalized_db_rows, BATCH_SIZE):
                statement = insert(NormalizedListing).values(normalized_batch)
                statement = statement.on_conflict_do_update(
                    index_elements=[NormalizedListing.source_object_id],
                    set_={
                        "listing_id": statement.excluded.listing_id,
                        "normalized_payload": statement.excluded.normalized_payload,
                        "validation_status": statement.excluded.validation_status,
                        "validation_errors": statement.excluded.validation_errors,
                        "validation_warnings": statement.excluded.validation_warnings,
                        "is_train_eligible": statement.excluded.is_train_eligible,
                    },
                )
                session.execute(statement)

            LOGGER.info("db_commit_start imported_rows=%s", stats.imported)
            session.commit()
            LOGGER.info("db_commit_done imported_rows=%s", stats.imported)
        except SQLAlchemyError:
            session.rollback()
            LOGGER.exception("db_commit_failed_rollback")
            raise

    LOGGER.info(
        "csv_read_done csv_path=%s processed=%s imported=%s skipped=%s",
        resolved_path,
        stats.processed,
        stats.imported,
        stats.skipped,
    )
    return stats
