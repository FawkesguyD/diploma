from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

import numpy as np
import pandas as pd
import requests
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from model.ml.model.feature_schema import NEW_DATASET_REQUIRED_COLUMNS, RUSSIA2021_DATASET_NAME
from model.ml.model.inference_validation import validate_inference_record
from model.ml.model.readiness import load_ready_model_bundle
from model.ml.model.runtime_adapters import build_listing_model_payload
from model.ml.model.settings import ARTIFACTS_DIR, RAW_DATA_DIR
from model.ml.model.utils import PROJECT_ROOT, ensure_directory
from model.shared.db.control_objects import get_control_object_sample_seed
from model.shared.db.models import AnalyticsControlObject, ShortlistItem, Valuation
from model.shared.db.session import SessionLocal, get_database_url


LOGGER = logging.getLogger("services.data_migrator.russia2021_control")
DEFAULT_SAMPLE_SIZE = int(os.getenv("CONTROL_SAMPLE_SIZE", "1000"))
DEFAULT_CHUNK_SIZE = int(os.getenv("RUSSIA2021_IMPORT_CHUNK_SIZE", "200000"))
DEFAULT_SOURCE_SPLIT = os.getenv("RUSSIA2021_SOURCE_SPLIT", "train")
DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH = RAW_DATA_DIR / "russia_real_estate_2021.csv"
DEFAULT_RUSSIA2021_PREPARED_DIR_NAME = "russia2021_prepared"
RUSSIA2021_LOG_TARGET_COLUMN = "target_log_price"
DEFAULT_PREPARED_DIR = ARTIFACTS_DIR / DEFAULT_RUSSIA2021_PREPARED_DIR_NAME
DEFAULT_MODEL_PATH = Path(os.getenv("MODEL_PATH", ARTIFACTS_DIR / "best_model_russia2021.joblib"))
DEFAULT_READINESS_PATH = Path(os.getenv("MODEL_READINESS_PATH", ARTIFACTS_DIR / "model_readiness.json"))
CONTROL_LISTING_ID_BASE = 2_021_000_000_000
CONTROL_LISTING_ID_RANGE = 900_000_000_000
SOURCE_MODES = Literal["auto", "csv", "hf", "prepared"]

RAW_SOURCE_COLUMNS = (
    "id",
    "listing_id",
    "external_id",
    "title",
    "address",
    "full_address",
    "city",
    "district",
    "districts",
    "condition",
    "seller_type",
    "user_type",
    "year_built",
    "url",
    "source_url",
    "rooms",
    "area",
    "total_area_m2",
    "kitchen_area",
    "kitchen_area_m2",
    "level",
    "floor",
    "levels",
    "total_floors",
    "price",
    "listing_price",
    "building_type",
    "object_type",
    "region",
    "latitude",
    "longitude",
    "geo_lat",
    "geo_lon",
)


@dataclass(slots=True)
class ControlPipelineStats:
    source_rows_read: int
    valid_candidate_rows: int
    selected_rows: int
    inserted_rows: int
    skipped_invalid_rows: int
    valuations_saved: int
    sample_size: int
    sample_seed: int
    source_description: str


def _project_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return PROJECT_ROOT / resolved


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _clean_text(value: Any) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if not _has_value(value):
        return None
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


def _first_value(row: dict[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        value = row.get(field_name)
        if _has_value(value):
            return value
    return None


def _first_float(row: dict[str, Any], *field_names: str) -> float | None:
    return _to_float(_first_value(row, *field_names))


def _first_int(row: dict[str, Any], *field_names: str) -> int | None:
    return _to_int(_first_value(row, *field_names))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if _has_value(item)}
    if isinstance(value, list):
        return [_json_safe(item) for item in value if _has_value(item)]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _stable_hex_key(source_object_id: str, sample_seed: int) -> str:
    return hashlib.sha256(f"{sample_seed}:{source_object_id}".encode("utf-8")).hexdigest()


def _stable_listing_id(source_object_id: str) -> int:
    digest_prefix = hashlib.sha256(source_object_id.encode("utf-8")).hexdigest()[:16]
    return CONTROL_LISTING_ID_BASE + (int(digest_prefix, 16) % CONTROL_LISTING_ID_RANGE)


def _source_object_id(row: dict[str, Any], *, source_label: str, row_index: int) -> str:
    for field_name in ("id", "listing_id", "external_id"):
        value = _clean_text(row.get(field_name))
        if value is not None:
            return f"{RUSSIA2021_DATASET_NAME}:{DEFAULT_SOURCE_SPLIT}:{value}"

    source_url = _clean_text(_first_value(row, "source_url", "url"))
    if source_url is not None:
        return f"{RUSSIA2021_DATASET_NAME}:{DEFAULT_SOURCE_SPLIT}:{source_url}"

    return f"{source_label}:{row_index}"


def _source_price(row: dict[str, Any]) -> float | None:
    price = _first_float(row, "listing_price", "price")
    if price is not None:
        return price

    log_price = _to_float(row.get(RUSSIA2021_LOG_TARGET_COLUMN))
    if log_price is None:
        return None
    return math.exp(log_price)


def _available_columns(columns: list[str] | pd.Index) -> list[str]:
    available = set(columns)
    return [column for column in RAW_SOURCE_COLUMNS if column in available]


def _download_russia2021_dataset(
    destination_path: Path,
    source_url: str | None,
    *,
    chunk_size: int = 1024 * 1024,
) -> Path:
    if destination_path.exists():
        return destination_path
    if not source_url:
        raise FileNotFoundError(
            "Файл датасета Russia_Real_Estate_2021 не найден. "
            "Передайте --russia-data-path, --russia-data-url/RUSSIA2021_DATA_URL, "
            "или используйте --source prepared."
        )

    ensure_directory(destination_path.parent)
    response = requests.get(source_url, stream=True, timeout=120)
    response.raise_for_status()
    with destination_path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)
    return destination_path


def _read_russia2021_header(dataset_path: Path) -> list[str]:
    header = pd.read_csv(dataset_path, nrows=0)
    return list(header.columns)


def _validate_russia2021_schema(columns: list[str] | pd.Index) -> None:
    available = set(columns)
    missing = [column for column in NEW_DATASET_REQUIRED_COLUMNS if column not in available]
    if missing:
        raise ValueError(
            "Некорректная схема датасета Russia_Real_Estate_2021. "
            f"Отсутствуют колонки: {', '.join(missing)}."
        )


def _iter_csv_rows(data_path: Path, *, chunk_size: int) -> Iterator[tuple[str, int, dict[str, Any]]]:
    header = _read_russia2021_header(data_path)
    _validate_russia2021_schema(header)
    source_columns = _available_columns(header)
    source_label = f"{RUSSIA2021_DATASET_NAME}:{data_path.name}"
    row_index = 0
    for chunk in pd.read_csv(data_path, usecols=source_columns, chunksize=chunk_size):
        for row in chunk.to_dict(orient="records"):
            yield source_label, row_index, row
            row_index += 1


def _iter_hf_rows(*, split: str) -> Iterator[tuple[str, int, dict[str, Any]]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError("Для загрузки Russia 2021 из HuggingFace нужен пакет datasets.") from exc

    dataset = load_dataset(RUSSIA2021_DATASET_NAME, split=split, streaming=True)
    iterator = iter(dataset)
    try:
        first_row = next(iterator)
    except StopIteration as exc:
        raise RuntimeError("HuggingFace dataset Russia 2021 пуст.") from exc

    _validate_russia2021_schema(first_row.keys())
    source_columns = _available_columns(first_row.keys())
    source_label = f"{RUSSIA2021_DATASET_NAME}:{split}"
    yield source_label, 0, {column: first_row.get(column) for column in source_columns}

    for row_index, row in enumerate(iterator, start=1):
        yield source_label, row_index, {column: row.get(column) for column in source_columns}


def _iter_prepared_pool_rows(prepared_dir: Path, *, chunk_size: int) -> Iterator[tuple[str, int, dict[str, Any]]]:
    pool_paths = (
        ("train_pool", prepared_dir / "train_pool.csv"),
        ("valid_pool", prepared_dir / "valid_pool.csv"),
    )
    for pool_name, pool_path in pool_paths:
        if not pool_path.exists():
            continue
        header = pd.read_csv(pool_path, nrows=0).columns
        use_columns = [
            column
            for column in (
                RUSSIA2021_LOG_TARGET_COLUMN,
                "rooms",
                "area",
                "kitchen_area",
                "level",
                "levels",
                "latitude",
                "longitude",
                "building_type",
                "object_type",
                "region",
            )
            if column in header
        ]
        source_label = f"{RUSSIA2021_DATASET_NAME}:prepared:{pool_name}"
        row_index = 0
        for chunk in pd.read_csv(pool_path, usecols=use_columns, chunksize=chunk_size):
            for row in chunk.to_dict(orient="records"):
                yield source_label, row_index, row
                row_index += 1


def _iter_source_rows(
    *,
    source: SOURCE_MODES,
    data_path: Path,
    source_url: str | None,
    prepared_dir: Path,
    split: str,
    chunk_size: int,
) -> tuple[str, Iterator[tuple[str, int, dict[str, Any]]]]:
    if source == "csv":
        if not data_path.exists():
            downloaded = _download_russia2021_dataset(data_path, source_url)
            data_path = downloaded
        return str(data_path), _iter_csv_rows(data_path, chunk_size=chunk_size)

    if source == "hf":
        return f"{RUSSIA2021_DATASET_NAME}:{split}", _iter_hf_rows(split=split)

    if source == "prepared":
        return str(prepared_dir), _iter_prepared_pool_rows(prepared_dir, chunk_size=chunk_size)

    if data_path.exists() or source_url:
        if not data_path.exists():
            data_path = _download_russia2021_dataset(data_path, source_url)
        return str(data_path), _iter_csv_rows(data_path, chunk_size=chunk_size)

    if (prepared_dir / "train_pool.csv").exists() or (prepared_dir / "valid_pool.csv").exists():
        return str(prepared_dir), _iter_prepared_pool_rows(prepared_dir, chunk_size=chunk_size)

    return f"{RUSSIA2021_DATASET_NAME}:{split}", _iter_hf_rows(split=split)


def _build_source_payload(row: dict[str, Any], *, source_label: str, row_index: int) -> dict[str, Any]:
    payload = _json_safe(row)
    if not isinstance(payload, dict):
        payload = {}
    payload["source_dataset"] = RUSSIA2021_DATASET_NAME
    payload["source_label"] = source_label
    payload["source_row_index"] = row_index
    return payload


def _build_control_candidate(
    row: dict[str, Any],
    *,
    source_label: str,
    row_index: int,
    sample_seed: int,
    bundle: Any,
) -> dict[str, Any] | None:
    listing_price = _source_price(row)
    area = _first_float(row, "area", "total_area_m2")
    if listing_price is None or listing_price <= 0 or area is None:
        return None

    source_object_id = _source_object_id(row, source_label=source_label, row_index=row_index)
    listing_id = _stable_listing_id(source_object_id)
    floor = _first_int(row, "floor", "level")
    total_floors = _first_int(row, "total_floors", "levels")
    kitchen_area = _first_float(row, "kitchen_area", "kitchen_area_m2")
    title = _clean_text(_first_value(row, "title", "address", "full_address"))
    district = _clean_text(_first_value(row, "district", "districts"))
    seller_type = _clean_text(_first_value(row, "seller_type", "user_type"))
    source_url = _clean_text(_first_value(row, "source_url", "url"))

    scoring_row = {
        "listing_id": listing_id,
        "listing_price": listing_price,
        "listing_currency": "RUB",
        "title": title,
        "city": _clean_text(row.get("city")),
        "district": district,
        "rooms": _first_int(row, "rooms"),
        "area": area,
        "kitchen_area_m2": kitchen_area,
        "floor": floor,
        "total_floors": total_floors,
        "building_type": _first_value(row, "building_type"),
        "object_type": _first_value(row, "object_type"),
        "region": _first_value(row, "region"),
        "condition": _clean_text(row.get("condition")),
        "year_built": _first_int(row, "year_built"),
        "seller_type": seller_type,
        "latitude": _first_float(row, "latitude", "geo_lat"),
        "longitude": _first_float(row, "longitude", "geo_lon"),
        "source_url": source_url,
    }
    model_payload = build_listing_model_payload(scoring_row, bundle, listing_currency="RUB")
    validation = validate_inference_record(model_payload, bundle.feature_config, bundle.metadata)
    if not validation.is_valid:
        return None

    normalized = validation.normalized_features
    sample_key = _stable_hex_key(source_object_id, sample_seed)
    return {
        "sample_key": sample_key,
        "source_object_id": source_object_id,
        "normalized_listing_id": None,
        "raw_listing_id": None,
        "listing_id": listing_id,
        "listing_price": listing_price,
        "listing_currency": "RUB",
        "target_proxy_price": listing_price,
        "target_source": "russia_2021_listing_price_proxy",
        "title": title,
        "city": _clean_text(scoring_row.get("city")),
        "district": district,
        "area": _to_float(normalized.get("area")),
        "rooms": _to_int(normalized.get("rooms")),
        "kitchen_area": _to_float(normalized.get("kitchen_area")),
        "level": _to_int(normalized.get("level")),
        "levels": _to_int(normalized.get("levels")),
        "floor": _to_int(normalized.get("level")),
        "total_floors": _to_int(normalized.get("levels")),
        "building_type": _clean_text(normalized.get("building_type")),
        "condition": _clean_text(scoring_row.get("condition")),
        "year_built": _to_int(scoring_row.get("year_built")),
        "seller_type": seller_type,
        "object_type": _clean_text(normalized.get("object_type")),
        "region": _clean_text(normalized.get("region")),
        "latitude": _to_float(normalized.get("latitude")),
        "longitude": _to_float(normalized.get("longitude")),
        "source_url": source_url,
        "source_payload": _build_source_payload(row, source_label=source_label, row_index=row_index),
        "sample_seed": sample_seed,
        "sample_rank": 0,
    }


def build_control_sample_rows(
    *,
    sample_size: int,
    sample_seed: int,
    source: SOURCE_MODES,
    data_path: Path,
    source_url: str | None,
    prepared_dir: Path,
    split: str,
    chunk_size: int,
    bundle: Any,
) -> tuple[list[dict[str, Any]], int, int, int, str]:
    source_description, row_iterator = _iter_source_rows(
        source=source,
        data_path=data_path,
        source_url=source_url,
        prepared_dir=prepared_dir,
        split=split,
        chunk_size=chunk_size,
    )
    heap: list[tuple[int, str, dict[str, Any]]] = []
    rows_read = 0
    valid_candidates = 0
    skipped_invalid = 0

    for source_label, row_index, row in row_iterator:
        rows_read += 1
        candidate = _build_control_candidate(
            row,
            source_label=source_label,
            row_index=row_index,
            sample_seed=sample_seed,
            bundle=bundle,
        )
        if candidate is None:
            skipped_invalid += 1
            continue

        valid_candidates += 1
        key_int = int(candidate["sample_key"], 16)
        heap_entry = (-key_int, candidate["source_object_id"], candidate)
        if len(heap) < sample_size:
            heapq.heappush(heap, heap_entry)
        elif heap_entry[0] > heap[0][0]:
            heapq.heapreplace(heap, heap_entry)

    selected_rows = [entry[2] for entry in heap]
    selected_rows.sort(key=lambda item: (item["sample_key"], item["source_object_id"]))
    for sample_rank, row in enumerate(selected_rows, start=1):
        row["sample_rank"] = sample_rank
        row.pop("sample_key", None)

    return selected_rows, rows_read, valid_candidates, skipped_invalid, source_description


def replace_control_rows(session: Session, rows: list[dict[str, Any]], *, sample_seed: int) -> int:
    old_listing_ids = [
        int(row.listing_id)
        for row in session.execute(
            select(func.coalesce(AnalyticsControlObject.listing_id, AnalyticsControlObject.id).label("listing_id"))
            .where(AnalyticsControlObject.sample_seed == sample_seed)
        )
    ]
    if old_listing_ids:
        session.execute(delete(ShortlistItem).where(ShortlistItem.listing_id.in_(old_listing_ids)))
        session.execute(delete(Valuation).where(Valuation.listing_id.in_(old_listing_ids)))

    # MVP import is delete+refill per sample_seed: this is deterministic, simple to reason about,
    # and avoids duplicate control rows on repeated runs.
    session.execute(delete(AnalyticsControlObject).where(AnalyticsControlObject.sample_seed == sample_seed))
    if not rows:
        return 0

    statement = insert(AnalyticsControlObject).values(rows)
    updatable_columns = (
        "normalized_listing_id",
        "raw_listing_id",
        "listing_id",
        "listing_price",
        "listing_currency",
        "target_proxy_price",
        "target_source",
        "title",
        "city",
        "district",
        "area",
        "rooms",
        "kitchen_area",
        "level",
        "levels",
        "floor",
        "total_floors",
        "building_type",
        "condition",
        "year_built",
        "seller_type",
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
            **{column_name: getattr(statement.excluded, column_name) for column_name in updatable_columns},
            "updated_at": func.now(),
        },
    )
    session.execute(statement)
    return len(rows)


def run_russia2021_control_pipeline(
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    sample_seed: int | None = None,
    source: SOURCE_MODES = "auto",
    data_path: Path | None = None,
    source_url: str | None = None,
    prepared_dir: Path = DEFAULT_PREPARED_DIR,
    split: str = DEFAULT_SOURCE_SPLIT,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    include_explanations: bool = False,
) -> ControlPipelineStats:
    resolved_seed = get_control_object_sample_seed() if sample_seed is None else sample_seed
    resolved_data_path = data_path or _project_path(os.getenv("RUSSIA2021_DATA_PATH")) or DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH
    resolved_source_url = source_url if source_url is not None else os.getenv("RUSSIA2021_DATA_URL")
    bundle = load_ready_model_bundle(
        configured_model_path=DEFAULT_MODEL_PATH,
        manifest_path=DEFAULT_READINESS_PATH,
        model_path_is_explicit=os.getenv("MODEL_PATH") is not None,
    )
    rows, rows_read, valid_candidates, skipped_invalid, source_description = build_control_sample_rows(
        sample_size=sample_size,
        sample_seed=resolved_seed,
        source=source,
        data_path=resolved_data_path,
        source_url=resolved_source_url,
        prepared_dir=prepared_dir,
        split=split,
        chunk_size=chunk_size,
        bundle=bundle,
    )
    if len(rows) < sample_size:
        raise RuntimeError(
            "Недостаточно валидных Russia 2021 строк для контрольного набора: "
            f"нужно {sample_size}, найдено {len(rows)} из {valid_candidates} валидных кандидатов."
        )

    with SessionLocal() as session:
        inserted_rows = replace_control_rows(session, rows, sample_seed=resolved_seed)

        from model.apps.api import api as runtime_api

        runtime_api.CONTROL_OBJECT_SAMPLE_SEED = resolved_seed
        valuations_saved = runtime_api.ensure_listing_valuations(
            session,
            only_missing=False,
            include_explanations=include_explanations,
        )

    stats = ControlPipelineStats(
        source_rows_read=rows_read,
        valid_candidate_rows=valid_candidates,
        selected_rows=len(rows),
        inserted_rows=inserted_rows,
        skipped_invalid_rows=skipped_invalid,
        valuations_saved=valuations_saved,
        sample_size=sample_size,
        sample_seed=resolved_seed,
        source_description=source_description,
    )
    LOGGER.info(
        "russia2021_control_pipeline_done source_rows_read=%s valid_candidate_rows=%s selected_rows=%s "
        "inserted_rows=%s skipped_invalid_rows=%s valuations_saved=%s sample_seed=%s source=%s",
        stats.source_rows_read,
        stats.valid_candidate_rows,
        stats.selected_rows,
        stats.inserted_rows,
        stats.skipped_invalid_rows,
        stats.valuations_saved,
        stats.sample_seed,
        stats.source_description,
    )
    return stats


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import deterministic Russia 2021 control objects and backfill proxy valuations.",
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--sample-seed", type=int, default=get_control_object_sample_seed())
    parser.add_argument("--source", choices=["auto", "csv", "hf", "prepared"], default="auto")
    parser.add_argument("--russia-data-path", type=Path, default=None)
    parser.add_argument("--russia-data-url", default=None)
    parser.add_argument("--prepared-dir", type=Path, default=DEFAULT_PREPARED_DIR)
    parser.add_argument("--split", default=DEFAULT_SOURCE_SPLIT)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--include-explanations", action="store_true")
    parser.add_argument("--run-migrations", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = _parse_args()
    if args.run_migrations:
        from model.services.data_migrator.bootstrap import run_migrations, wait_for_database

        database_url = get_database_url()
        wait_for_database(database_url)
        run_migrations(database_url)

    stats = run_russia2021_control_pipeline(
        sample_size=args.sample_size,
        sample_seed=args.sample_seed,
        source=args.source,
        data_path=_project_path(args.russia_data_path),
        source_url=args.russia_data_url,
        prepared_dir=args.prepared_dir,
        split=args.split,
        chunk_size=args.chunk_size,
        include_explanations=args.include_explanations,
    )
    print(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
