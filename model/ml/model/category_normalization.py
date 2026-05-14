from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd


CATEGORY_UNKNOWN = "unknown"
CATEGORY_MISSING = "missing"

BUILDING_TYPE_MAPPING: dict[str, str] = {
    "0": CATEGORY_UNKNOWN,
    "1": "other",
    "2": "panel",
    "3": "monolith",
    "4": "brick",
    "5": "block",
    "6": "wooden",
    CATEGORY_UNKNOWN: CATEGORY_UNKNOWN,
    CATEGORY_MISSING: CATEGORY_MISSING,
    "dont_know": CATEGORY_UNKNOWN,
    "unknown": CATEGORY_UNKNOWN,
    "other": "other",
    "panel": "panel",
    "панель": "panel",
    "панельный": "panel",
    "monolith": "monolith",
    "monolithic": "monolith",
    "монолит": "monolith",
    "монолитный": "monolith",
    "brick": "brick",
    "кирпич": "brick",
    "кирпичный": "brick",
    "block": "block",
    "blocky": "block",
    "блок": "block",
    "блочный": "block",
    "wood": "wooden",
    "wooden": "wooden",
    "дерево": "wooden",
    "деревянный": "wooden",
}

OBJECT_TYPE_MAPPING: dict[str, str] = {
    "0": "secondary",
    "1": "secondary",
    "2": "new",
    "11": "new",
    "secondary": "secondary",
    "resale": "secondary",
    "old": "secondary",
    "вторичка": "secondary",
    "вторичный": "secondary",
    "new": "new",
    "newbuilding": "new",
    "new_building": "new",
    "новостройка": "new",
    "новый": "new",
    CATEGORY_UNKNOWN: CATEGORY_UNKNOWN,
    CATEGORY_MISSING: CATEGORY_MISSING,
}

CANONICAL_CATEGORY_VALUES: dict[str, set[str]] = {
    "building_type": set(BUILDING_TYPE_MAPPING.values()),
    "object_type": set(OBJECT_TYPE_MAPPING.values()),
}

DEFAULT_RUSSIA2021_REGION_CODES: set[str] = {
    "3",
    "69",
    "81",
    "821",
    "1010",
    "1491",
    "1901",
    "2072",
    "2328",
    "2359",
    "2484",
    "2528",
    "2594",
    "2604",
    "2661",
    "2722",
    "2806",
    "2814",
    "2843",
    "2860",
    "2871",
    "2880",
    "2885",
    "2900",
    "2922",
    "3019",
    "3106",
    "3153",
    "3230",
    "3446",
    "3870",
    "3991",
    "4007",
    "4086",
    "4189",
    "4240",
    "4249",
    "4374",
    "4417",
    "4695",
    "4963",
    "4982",
    "5143",
    "5178",
    "5241",
    "5282",
    "5368",
    "5520",
    "5703",
    "5736",
    "5789",
    "5794",
    "5952",
    "5993",
    "6171",
    "6309",
    "6543",
    "6817",
    "6937",
    "7121",
    "7793",
    "7873",
    "7896",
    "7929",
    "8090",
    "8509",
    "8640",
    "8894",
    "9579",
    "9648",
    "9654",
    "10160",
    "10201",
    "10582",
    "11171",
    "11416",
    "11991",
    "13098",
    "13913",
    "13919",
    "14368",
    "14880",
    "16705",
    "61888",
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _normalize_token(value: Any) -> str | None:
    if not _has_value(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().lower()


def normalize_category_value(field_name: str, value: Any) -> tuple[str | None, bool]:
    token = _normalize_token(value)
    if token is None or token == "":
        return None, True

    mapping = {
        "building_type": BUILDING_TYPE_MAPPING,
        "object_type": OBJECT_TYPE_MAPPING,
    }.get(field_name)
    if mapping is None:
        return str(value).strip(), True

    normalized = mapping.get(token)
    if normalized is None:
        return str(value).strip(), False
    return normalized, True


def normalize_region_value(value: Any) -> str | None:
    token = _normalize_token(value)
    if token is None:
        return None
    if token.endswith(".0"):
        token = token[:-2]
    return token


def normalize_categories_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(record)
    invalid_fields: list[str] = []

    for field_name in ("building_type", "object_type"):
        if field_name not in normalized:
            continue
        category_value, is_known = normalize_category_value(field_name, normalized.get(field_name))
        if category_value is not None:
            normalized[field_name] = category_value
        if not is_known:
            invalid_fields.append(field_name)

    if "region" in normalized:
        region = normalize_region_value(normalized.get("region"))
        if region is not None:
            normalized["region"] = region

    return normalized, invalid_fields


def normalize_category_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    normalized = frame.copy()
    invalid_counts: dict[str, int] = {}

    for field_name in ("building_type", "object_type"):
        if field_name not in normalized.columns:
            continue

        values: list[str | None] = []
        invalid_count = 0
        for value in normalized[field_name].tolist():
            category_value, is_known = normalize_category_value(field_name, value)
            values.append(category_value if category_value is not None else CATEGORY_MISSING)
            if not is_known:
                invalid_count += 1
        normalized[field_name] = values
        invalid_counts[field_name] = invalid_count

    if "region" in normalized.columns:
        normalized["region"] = normalized["region"].map(
            lambda value: normalize_region_value(value) or CATEGORY_MISSING
        )

    return normalized, invalid_counts


def allowed_regions_from_metadata(metadata: dict[str, Any] | None) -> set[str]:
    if not metadata:
        return set(DEFAULT_RUSSIA2021_REGION_CODES)

    raw_values = (
        metadata.get("allowed_regions")
        or metadata.get("region_values")
        or metadata.get("category_values", {}).get("region")
    )
    if raw_values is None:
        return set(DEFAULT_RUSSIA2021_REGION_CODES)

    if isinstance(raw_values, str):
        return {raw_values}
    if isinstance(raw_values, Iterable):
        return {str(value) for value in raw_values if value is not None}
    return set(DEFAULT_RUSSIA2021_REGION_CODES)
