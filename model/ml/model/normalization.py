from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from model.ml.model.category_normalization import normalize_category_frame
from model.ml.model.feature_schema import (
    DERIVED_NUMERIC_FEATURES,
    FEATURE_ALIASES,
    FLOOR_COLUMN,
    KITCHEN_AREA_COLUMN,
    GEO_LAT_COLUMN,
    GEO_LON_COLUMN,
    LATITUDE_COLUMN,
    LEVEL_COLUMN,
    LEVELS_COLUMN,
    LONGITUDE_COLUMN,
    NEW_KITCHEN_AREA_COLUMN,
    LISTING_PRICE_COLUMN,
    REFERENCE_YEAR,
    TOTAL_AREA_COLUMN,
    TOTAL_FLOORS_COLUMN,
    AREA_COLUMN,
    FeatureConfig,
    expected_columns_for_config,
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _with_source_columns(expected_columns: set[str]) -> set[str]:
    columns = set(expected_columns)
    if {"area_per_room", "rooms_density", "is_studio"} & columns:
        columns.update({TOTAL_AREA_COLUMN, AREA_COLUMN, "rooms"})
    if "kitchen_ratio" in columns:
        columns.update({TOTAL_AREA_COLUMN, AREA_COLUMN, KITCHEN_AREA_COLUMN, NEW_KITCHEN_AREA_COLUMN})
    if {"floor_ratio", "is_top_floor", "is_first_floor"} & columns:
        columns.update({FLOOR_COLUMN, LEVEL_COLUMN, TOTAL_FLOORS_COLUMN, LEVELS_COLUMN})
    if "building_age" in columns:
        columns.add("year_built")
    if "has_coordinates" in columns:
        columns.update({LATITUDE_COLUMN, LONGITUDE_COLUMN, GEO_LAT_COLUMN, GEO_LON_COLUMN})
    return columns


def normalize_feature_record(
    object_features: dict[str, Any],
    feature_config: FeatureConfig | None = None,
) -> dict[str, Any]:
    normalized = dict(object_features)
    expected_columns = (
        _with_source_columns(expected_columns_for_config(feature_config))
        if feature_config is not None
        else set(FEATURE_ALIASES)
    )

    for canonical_name, aliases in FEATURE_ALIASES.items():
        if canonical_name not in expected_columns:
            continue
        if _has_value(normalized.get(canonical_name)):
            continue
        for alias in aliases:
            if _has_value(normalized.get(alias)):
                normalized[canonical_name] = normalized[alias]
                break

    return normalized


def normalize_feature_frame(
    frame: pd.DataFrame,
    feature_config: FeatureConfig,
) -> pd.DataFrame:
    normalized = frame.copy()
    expected_columns = _with_source_columns(expected_columns_for_config(feature_config))

    for canonical_name, aliases in FEATURE_ALIASES.items():
        if canonical_name not in expected_columns:
            continue
        for alias in aliases:
            if alias in normalized.columns:
                if canonical_name in normalized.columns:
                    normalized[canonical_name] = normalized[canonical_name].combine_first(normalized[alias])
                else:
                    normalized[canonical_name] = normalized[alias]
                break

    return normalized


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numeric_numerator = pd.to_numeric(numerator, errors="coerce")
    numeric_denominator = pd.to_numeric(denominator, errors="coerce").replace({0: np.nan})
    result = numeric_numerator / numeric_denominator
    return result.replace([np.inf, -np.inf], np.nan)


def _first_available_series(features: pd.DataFrame, columns: list[str]) -> pd.Series | None:
    available = [column for column in columns if column in features.columns]
    if not available:
        return None

    result = pd.to_numeric(features[available[0]], errors="coerce")
    for column in available[1:]:
        result = result.combine_first(pd.to_numeric(features[column], errors="coerce"))
    return result


def _normalize_rooms(features: pd.DataFrame) -> None:
    if "rooms" not in features.columns:
        features["is_studio"] = np.nan
        return

    rooms = pd.to_numeric(features["rooms"], errors="coerce")
    studio_mask = rooms <= 0
    features["is_studio"] = studio_mask.astype(float)
    features["rooms"] = rooms.mask(studio_mask, 1.0)


def fill_categorical_features_for_catboost(
    frame: pd.DataFrame,
    categorical_features: list[str],
) -> pd.DataFrame:
    prepared = frame.copy()
    for column in categorical_features:
        if column in prepared.columns:
            prepared[column] = prepared[column].where(prepared[column].notna(), "missing").astype(str)
    return prepared


def create_model_features(df: pd.DataFrame, feature_config: FeatureConfig) -> pd.DataFrame:
    features = normalize_feature_frame(df, feature_config)
    features, _ = normalize_category_frame(features)
    _normalize_rooms(features)

    for column in feature_config.feature_columns:
        if column not in features.columns and column not in feature_config.derived_numeric_features:
            features[column] = np.nan

    area = _first_available_series(features, [AREA_COLUMN, TOTAL_AREA_COLUMN])
    kitchen_area = _first_available_series(features, [NEW_KITCHEN_AREA_COLUMN, KITCHEN_AREA_COLUMN])
    level = _first_available_series(features, [LEVEL_COLUMN, FLOOR_COLUMN])
    levels = _first_available_series(features, [LEVELS_COLUMN, TOTAL_FLOORS_COLUMN])

    if area is not None and "rooms" in features.columns:
        features["area_per_room"] = safe_divide(area, features["rooms"])
        features["rooms_density"] = safe_divide(features["rooms"], area)
    else:
        features["area_per_room"] = np.nan
        features["rooms_density"] = np.nan

    if area is not None and kitchen_area is not None:
        features["kitchen_ratio"] = safe_divide(kitchen_area, area)
    else:
        features["kitchen_ratio"] = np.nan

    if level is not None and levels is not None:
        features["floor_ratio"] = safe_divide(level, levels)
        valid_floor_pair = level.notna() & levels.notna()
        features["is_top_floor"] = np.where(valid_floor_pair, (level == levels).astype(float), np.nan)
        features["is_first_floor"] = np.where(level.notna(), (level == 1).astype(float), np.nan)
    else:
        features["floor_ratio"] = np.nan
        features["is_top_floor"] = np.nan
        features["is_first_floor"] = np.nan

    if "year_built" in features.columns:
        features["building_age"] = REFERENCE_YEAR - features["year_built"]
        features.loc[features["building_age"] < 0, "building_age"] = np.nan
    else:
        features["building_age"] = np.nan

    if {"latitude", "longitude"}.issubset(features.columns):
        features["has_coordinates"] = (
            features["latitude"].notna() & features["longitude"].notna()
        ).astype(float)
    else:
        features["has_coordinates"] = 0.0

    model_frame = features.loc[:, feature_config.feature_columns].copy()

    for column in feature_config.numerical_features:
        if column in model_frame.columns:
            model_frame[column] = pd.to_numeric(model_frame[column], errors="coerce")

    for column in feature_config.categorical_features:
        model_frame[column] = model_frame[column].astype("object")

    return model_frame


def prepare_objects_frame(
    objects: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
) -> pd.DataFrame:
    if isinstance(objects, dict):
        return pd.DataFrame([objects])
    if isinstance(objects, list):
        return pd.DataFrame(objects)
    return objects.copy()


def derived_feature_names() -> list[str]:
    return list(DERIVED_NUMERIC_FEATURES)
