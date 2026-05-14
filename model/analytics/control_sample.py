from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from model.analytics.config import AnalyticsConfig, ANALYTICS_ROOT
from model.analytics.data_access.db import load_normalized_dataset
from model.shared.db.session import create_db_engine


CONTROL_SAMPLE_TABLE = "analytics_control_objects"
CONTROL_SAMPLE_SQL_PATH = ANALYTICS_ROOT / "sql" / "control_sample.sql"


@dataclass(slots=True)
class ControlSampleStats:
    source_rows: int
    candidate_rows: int
    inserted_rows: int
    sample_size: int
    sample_seed: int
    source_description: str


def _split_sql_script(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current))
    return statements


def ensure_control_sample_table(engine: Engine, sql_path: Path = CONTROL_SAMPLE_SQL_PATH) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in _split_sql_script(sql_text):
            connection.execute(text(statement))


def _stable_sample_key(source_object_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{source_object_id}".encode("utf-8")).hexdigest()


def _source_object_id(row: pd.Series) -> str:
    source_object_id = row.get("source_object_id")
    if pd.notna(source_object_id) and str(source_object_id).strip():
        return str(source_object_id)
    listing_id = row.get("listing_id")
    if pd.notna(listing_id):
        return f"listing:{int(listing_id)}"
    raw_listing_id = row.get("raw_listing_id")
    if pd.notna(raw_listing_id):
        return f"raw:{int(raw_listing_id)}"
    normalized_id = row.get("normalized_id")
    if pd.notna(normalized_id):
        return f"normalized:{int(normalized_id)}"
    return f"row:{int(row.name)}"


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text_value = str(value).strip()
    return text_value or None


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return number


def _json_payload(row: pd.Series) -> str:
    payload = {
        "normalized_id": _optional_int(row.get("normalized_id")),
        "source_object_id": _clean_text(row.get("source_object_id")),
        "raw_listing_id": _optional_int(row.get("raw_listing_id")),
        "listing_id": _optional_int(row.get("listing_id")),
        "validation_status": _clean_text(row.get("validation_status")),
        "is_train_eligible": bool(row.get("is_train_eligible")),
        "validation_errors": row.get("validation_errors") or [],
        "validation_warnings": row.get("validation_warnings") or [],
        "title": _clean_text(row.get("title")),
        "district": _clean_text(row.get("district")),
        "city": _clean_text(row.get("city")),
    }
    return json.dumps(payload, ensure_ascii=False)


def _control_row(row: pd.Series, *, sample_seed: int, sample_rank: int) -> dict[str, Any]:
    listing_price = float(row["listing_price"])
    return {
        "source_object_id": row["source_object_id"],
        "normalized_listing_id": _optional_int(row.get("normalized_id")),
        "raw_listing_id": _optional_int(row.get("raw_listing_id")),
        "listing_id": _optional_int(row.get("listing_id")),
        "listing_price": listing_price,
        "listing_currency": _clean_text(row.get("listing_currency")) or "RUB",
        "target_proxy_price": listing_price,
        "target_source": "listing_price_proxy",
        "area": float(row["area"]),
        "rooms": _optional_int(row.get("rooms")),
        "kitchen_area": _optional_float(row.get("kitchen_area")),
        "level": _optional_int(row.get("level")),
        "levels": _optional_int(row.get("levels")),
        "building_type": _clean_text(row.get("building_type")),
        "object_type": _clean_text(row.get("object_type")),
        "region": _clean_text(row.get("region")),
        "latitude": _optional_float(row.get("latitude")),
        "longitude": _optional_float(row.get("longitude")),
        "source_url": _clean_text(row.get("source_url")),
        "source_payload": _json_payload(row),
        "sample_seed": sample_seed,
        "sample_rank": sample_rank,
    }


def build_control_sample_frame(
    config: AnalyticsConfig,
    *,
    sample_size: int,
    sample_seed: int,
) -> tuple[pd.DataFrame, int]:
    source_frame = load_normalized_dataset(config)
    if source_frame.empty:
        return source_frame, 0

    candidates = source_frame[
        (source_frame["is_train_eligible"])
        & (source_frame["listing_price"].notna())
        & (source_frame["listing_price"] > 0)
        & (source_frame["area"].notna())
        & (source_frame["area"] > 0)
        & (source_frame["listing_currency"].fillna("RUB").astype(str).str.upper() == "RUB")
    ].copy()
    if candidates.empty:
        return candidates, len(source_frame)

    candidates["source_object_id"] = candidates.apply(_source_object_id, axis=1)
    candidates = candidates.drop_duplicates(subset=["source_object_id"], keep="first")
    candidate_rows = int(len(candidates))
    candidates["sample_key"] = candidates["source_object_id"].map(
        lambda source_id: _stable_sample_key(source_id, sample_seed)
    )
    candidates = candidates.sort_values(["sample_key", "source_object_id"]).head(sample_size).reset_index(drop=True)
    candidates["sample_rank"] = np.arange(1, len(candidates) + 1)
    candidates.attrs["candidate_rows"] = candidate_rows
    candidates.attrs["source_description"] = source_frame.attrs.get("source_description", "")
    return candidates, len(source_frame)


def replace_control_sample_rows(
    engine: Engine,
    sample_frame: pd.DataFrame,
    *,
    sample_seed: int,
) -> int:
    rows = [
        _control_row(row, sample_seed=sample_seed, sample_rank=int(row["sample_rank"]))
        for _, row in sample_frame.iterrows()
    ]
    insert_statement = text(
        """
        insert into analytics_control_objects (
          source_object_id,
          normalized_listing_id,
          raw_listing_id,
          listing_id,
          listing_price,
          listing_currency,
          target_proxy_price,
          target_source,
          area,
          rooms,
          kitchen_area,
          level,
          levels,
          building_type,
          object_type,
          region,
          latitude,
          longitude,
          source_url,
          source_payload,
          sample_seed,
          sample_rank
        )
        values (
          :source_object_id,
          :normalized_listing_id,
          :raw_listing_id,
          :listing_id,
          :listing_price,
          :listing_currency,
          :target_proxy_price,
          :target_source,
          :area,
          :rooms,
          :kitchen_area,
          :level,
          :levels,
          :building_type,
          :object_type,
          :region,
          :latitude,
          :longitude,
          :source_url,
          cast(:source_payload as jsonb),
          :sample_seed,
          :sample_rank
        )
        on conflict (sample_seed, source_object_id) do update set
          normalized_listing_id = excluded.normalized_listing_id,
          raw_listing_id = excluded.raw_listing_id,
          listing_id = excluded.listing_id,
          listing_price = excluded.listing_price,
          listing_currency = excluded.listing_currency,
          target_proxy_price = excluded.target_proxy_price,
          target_source = excluded.target_source,
          area = excluded.area,
          rooms = excluded.rooms,
          kitchen_area = excluded.kitchen_area,
          level = excluded.level,
          levels = excluded.levels,
          building_type = excluded.building_type,
          object_type = excluded.object_type,
          region = excluded.region,
          latitude = excluded.latitude,
          longitude = excluded.longitude,
          source_url = excluded.source_url,
          source_payload = excluded.source_payload,
          sample_rank = excluded.sample_rank,
          updated_at = now()
        """
    )
    with engine.begin() as connection:
        connection.execute(
            text("delete from analytics_control_objects where sample_seed = :sample_seed"),
            {"sample_seed": sample_seed},
        )
        if rows:
            connection.execute(insert_statement, rows)
    return len(rows)


def bootstrap_control_sample(
    config: AnalyticsConfig,
    *,
    sample_size: int,
    sample_seed: int,
) -> ControlSampleStats:
    engine = create_db_engine(config.database_url)
    try:
        ensure_control_sample_table(engine)
        sample_frame, source_rows = build_control_sample_frame(
            config,
            sample_size=sample_size,
            sample_seed=sample_seed,
        )
        candidate_rows = int(sample_frame.attrs.get("candidate_rows", len(sample_frame)))
        if candidate_rows < sample_size:
            raise RuntimeError(
                "Недостаточно валидных строк для контрольной выборки: "
                f"нужно {sample_size}, найдено {candidate_rows}."
            )
        inserted_rows = replace_control_sample_rows(
            engine,
            sample_frame,
            sample_seed=sample_seed,
        )
        source_description = sample_frame.attrs.get("source_description", "")
        return ControlSampleStats(
            source_rows=source_rows,
            candidate_rows=candidate_rows,
            inserted_rows=inserted_rows,
            sample_size=sample_size,
            sample_seed=sample_seed,
            source_description=source_description,
        )
    finally:
        engine.dispose()
