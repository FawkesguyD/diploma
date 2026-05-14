from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import select

from model.ml.model.feature_schema import RUSSIA2021_SOURCE_COLUMNS
from model.ml.model.utils import ensure_directory
from model.shared.db.models import NormalizedListing
from model.shared.db.session import SessionLocal


DB_TRAINING_COLUMNS = [
    "rooms",
    "area",
    "kitchen_area",
    "level",
    "levels",
    "price",
    "latitude",
    "longitude",
    "building_type",
    "object_type",
    "region",
]


def _payload_value(payload: dict[str, Any], column_name: str) -> Any:
    if column_name == "price":
        return payload.get("price") or payload.get("listing_price") or payload.get("listing_price_rub")
    return payload.get(column_name)


def export_normalized_training_csv(
    output_path: Path,
    *,
    limit: int | None = None,
    batch_size: int = 10_000,
) -> dict[str, int | str]:
    ensure_directory(output_path.parent)
    exported_rows = 0
    selected_columns = [column for column in DB_TRAINING_COLUMNS if column in set(RUSSIA2021_SOURCE_COLUMNS + ["price"])]

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=selected_columns)
        writer.writeheader()

        with SessionLocal() as session:
            statement = (
                select(NormalizedListing.normalized_payload)
                .where(NormalizedListing.is_train_eligible.is_(True))
                .order_by(NormalizedListing.id.asc())
            )
            if limit is not None:
                statement = statement.limit(limit)

            for row in session.execute(statement).yield_per(batch_size):
                payload = row[0] or {}
                writer.writerow(
                    {
                        column_name: _payload_value(payload, column_name)
                        for column_name in selected_columns
                    }
                )
                exported_rows += 1

    return {
        "output_path": str(output_path),
        "rows_exported": exported_rows,
    }
