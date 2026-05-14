from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from model.ml.model.category_normalization import (
    CATEGORY_MISSING,
    CATEGORY_UNKNOWN,
    allowed_regions_from_metadata,
    normalize_categories_record,
)
from model.ml.model.feature_schema import (
    AREA_COLUMN,
    FLOOR_COLUMN,
    KITCHEN_AREA_COLUMN,
    LEVEL_COLUMN,
    LEVELS_COLUMN,
    NEW_KITCHEN_AREA_COLUMN,
    TOTAL_AREA_COLUMN,
    TOTAL_FLOORS_COLUMN,
    FeatureConfig,
)
from model.ml.model.normalization import normalize_feature_record


ConfidenceLevel = Literal["high", "medium", "low"]

MIN_AREA_M2 = 10.0
MAX_AREA_M2 = 500.0
SMALL_AREA_M2 = 20.0
ROOM_AREA_RATIO_M2 = 8.0
MAX_ROOMS = 10
MAX_LEVELS = 100
RUSSIA_MIN_LATITUDE = 41.0
RUSSIA_MAX_LATITUDE = 82.0
RUSSIA_MIN_LONGITUDE = 19.0
RUSSIA_MAX_LONGITUDE = 180.0


@dataclass(slots=True)
class InputValidationResult:
    normalized_features: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: ConfidenceLevel = "high"

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _coerce_float(value: Any) -> float | None:
    if not _has_value(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _coerce_int(value: Any) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(number)


def _first_number(record: dict[str, Any], *field_names: str) -> float | None:
    for field_name in field_names:
        value = _coerce_float(record.get(field_name))
        if value is not None:
            return value
    return None


def _first_int(record: dict[str, Any], *field_names: str) -> int | None:
    for field_name in field_names:
        value = _coerce_int(record.get(field_name))
        if value is not None:
            return value
    return None


def _degrade_confidence(
    current: ConfidenceLevel,
    target: ConfidenceLevel,
) -> ConfidenceLevel:
    order = {"high": 0, "medium": 1, "low": 2}
    return target if order[target] > order[current] else current


def _check_area_layout(record: dict[str, Any], result: InputValidationResult) -> None:
    area = _first_number(record, AREA_COLUMN, TOTAL_AREA_COLUMN)
    kitchen_area = _first_number(record, NEW_KITCHEN_AREA_COLUMN, KITCHEN_AREA_COLUMN)
    rooms = _first_int(record, "rooms")

    if area is None:
        result.errors.append("Не указана общая площадь объекта.")
        return

    if area <= 0:
        result.errors.append("Общая площадь должна быть больше 0 м².")
    elif area < MIN_AREA_M2:
        result.errors.append(f"Общая площадь меньше минимально допустимых {MIN_AREA_M2:g} м².")
    elif area > MAX_AREA_M2:
        result.errors.append(f"Общая площадь больше максимально допустимых {MAX_AREA_M2:g} м² для квартирной модели.")
    elif area < SMALL_AREA_M2:
        result.warnings.append("Очень маленькая площадь: оценка будет менее устойчивой.")
        result.confidence = _degrade_confidence(result.confidence, "medium")

    if kitchen_area is None:
        result.warnings.append("Не указана площадь кухни.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
    elif kitchen_area < 0:
        result.errors.append("Площадь кухни не может быть отрицательной.")
    elif area is not None and kitchen_area > area:
        result.errors.append("Площадь кухни не может быть больше общей площади.")
    elif area is not None and area > 0 and kitchen_area / area > 0.55:
        result.warnings.append("Площадь кухни занимает необычно большую долю общей площади.")
        result.confidence = _degrade_confidence(result.confidence, "medium")

    if rooms is None:
        result.warnings.append("Не указано количество комнат.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
    elif rooms < 0:
        result.errors.append("Количество комнат должно быть неотрицательным.")
    elif rooms > MAX_ROOMS:
        result.errors.append(f"Количество комнат больше максимально допустимого значения {MAX_ROOMS}.")
    elif area is not None and area > 0 and rooms > max(1, int(area // ROOM_AREA_RATIO_M2)):
        result.errors.append(
            f"Количество комнат физически нереалистично для площади {area:.1f} м²."
        )


def _check_floor_layout(record: dict[str, Any], result: InputValidationResult) -> None:
    level = _first_int(record, LEVEL_COLUMN, FLOOR_COLUMN)
    levels = _first_int(record, LEVELS_COLUMN, TOTAL_FLOORS_COLUMN)

    if level is None:
        result.warnings.append("Не указан этаж объекта.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
    elif level < 1:
        result.errors.append("Этаж должен быть не меньше 1.")
    elif level > MAX_LEVELS:
        result.errors.append(f"Этаж больше максимально допустимого значения {MAX_LEVELS}.")

    if levels is None:
        result.warnings.append("Не указана этажность дома.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
    elif levels < 1:
        result.errors.append("Этажность дома должна быть не меньше 1.")
    elif levels > MAX_LEVELS:
        result.errors.append(f"Этажность дома больше максимально допустимого значения {MAX_LEVELS}.")

    if level is not None and levels is not None and level > levels:
        result.errors.append("Этаж объекта не может быть выше этажности дома.")


def _check_geo(record: dict[str, Any], result: InputValidationResult) -> None:
    latitude = _coerce_float(record.get("latitude"))
    longitude = _coerce_float(record.get("longitude"))

    if latitude is None or longitude is None:
        result.warnings.append("Координаты отсутствуют или заполнены не полностью.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
        return

    if not (RUSSIA_MIN_LATITUDE <= latitude <= RUSSIA_MAX_LATITUDE):
        result.errors.append("Широта находится вне допустимых границ РФ.")
    if not (RUSSIA_MIN_LONGITUDE <= longitude <= RUSSIA_MAX_LONGITUDE):
        result.errors.append("Долгота находится вне допустимых границ РФ.")


def _check_categories(
    record: dict[str, Any],
    result: InputValidationResult,
    feature_config: FeatureConfig,
    metadata: dict[str, Any] | None,
) -> None:
    expected_categories = set(feature_config.categorical_features) | {
        "building_type",
        "object_type",
        "region",
    }

    for field_name in ("building_type", "object_type"):
        if field_name not in expected_categories:
            continue
        value = record.get(field_name)
        if not _has_value(value):
            result.warnings.append(f"Категория {field_name} не указана.")
            result.confidence = _degrade_confidence(result.confidence, "medium")
            continue
        if value in {CATEGORY_UNKNOWN, CATEGORY_MISSING}:
            result.warnings.append(f"Категория {field_name} определена как {value}.")
            result.confidence = _degrade_confidence(result.confidence, "low")

    invalid_fields = record.get("__invalid_category_fields__") or []
    for field_name in invalid_fields:
        result.errors.append(f"Категория {field_name} не входит в поддерживаемый справочник.")

    if "region" not in expected_categories:
        return

    region = record.get("region")
    if not _has_value(region):
        result.warnings.append("Регион не указан.")
        result.confidence = _degrade_confidence(result.confidence, "medium")
        return

    allowed_regions = allowed_regions_from_metadata(metadata)
    if allowed_regions and str(region) not in allowed_regions:
        result.errors.append("Регион отсутствует в train pool активной модели.")


def validate_inference_record(
    object_features: dict[str, Any],
    feature_config: FeatureConfig,
    metadata: dict[str, Any] | None = None,
) -> InputValidationResult:
    normalized = normalize_feature_record(object_features, feature_config)
    normalized, invalid_category_fields = normalize_categories_record(normalized)
    if invalid_category_fields:
        normalized["__invalid_category_fields__"] = invalid_category_fields

    result = InputValidationResult(normalized_features=normalized)
    _check_area_layout(normalized, result)
    _check_floor_layout(normalized, result)
    _check_geo(normalized, result)
    _check_categories(normalized, result, feature_config, metadata)

    if result.errors:
        result.confidence = "low"
    elif len(result.warnings) >= 3:
        result.confidence = _degrade_confidence(result.confidence, "low")

    return result


def training_validity_mask(
    frame: pd.DataFrame,
    *,
    price_column: str,
    feature_config: FeatureConfig,
    metadata: dict[str, Any] | None = None,
) -> pd.Series:
    records = frame.to_dict(orient="records")
    valid_flags = []
    for record in records:
        price = _coerce_float(record.get(price_column))
        if price is None or price <= 0:
            valid_flags.append(False)
            continue
        validation = validate_inference_record(record, feature_config, metadata)
        valid_flags.append(validation.is_valid)
    return pd.Series(valid_flags, index=frame.index, dtype=bool)
