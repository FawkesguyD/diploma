from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


TARGET_COLUMN = "price_usd"
PRICE_USD_COLUMN = "price_usd"
PRICE_COLUMN = "price"
LISTING_PRICE_COLUMN = "listing_price"
DEFAULT_ARTIFACT_BASE_CURRENCY = "USD"
RUSSIA2021_BASE_CURRENCY = "RUB"

LEAKAGE_COLUMNS = ["price_per_m2_usd"]
IRRELEVANT_COLUMNS = [
    "listing_id",
    "url",
    "city",
    "address",
    "description",
    "parsed_at",
    "photos_downloaded",
]
TEXT_LIKE_COLUMNS = ["amenities", "documents", "security"]

REFERENCE_YEAR = datetime.now().year

TOTAL_AREA_COLUMN = "total_area_m2"
AREA_COLUMN = "area"
KITCHEN_AREA_COLUMN = "kitchen_area_m2"
NEW_KITCHEN_AREA_COLUMN = "kitchen_area"
FLOOR_COLUMN = "floor"
LEVEL_COLUMN = "level"
TOTAL_FLOORS_COLUMN = "total_floors"
LEVELS_COLUMN = "levels"
LATITUDE_COLUMN = "latitude"
LONGITUDE_COLUMN = "longitude"
GEO_LAT_COLUMN = "geo_lat"
GEO_LON_COLUMN = "geo_lon"

DERIVED_NUMERIC_FEATURES = [
    "is_studio",
    "area_per_room",
    "floor_ratio",
    "kitchen_ratio",
    "rooms_density",
    "building_age",
    "is_top_floor",
    "is_first_floor",
    "has_coordinates",
]

NEW_DATASET_REQUIRED_COLUMNS = [
    "rooms",
    AREA_COLUMN,
    NEW_KITCHEN_AREA_COLUMN,
    LEVEL_COLUMN,
    LEVELS_COLUMN,
    PRICE_COLUMN,
]
RUSSIA2021_FEATURE_COLUMNS = [
    "rooms",
    AREA_COLUMN,
    NEW_KITCHEN_AREA_COLUMN,
    LEVEL_COLUMN,
    LEVELS_COLUMN,
]
RUSSIA2021_OPTIONAL_NUMERIC_COLUMNS = [
    LATITUDE_COLUMN,
    LONGITUDE_COLUMN,
]
RUSSIA2021_SOURCE_COORDINATE_COLUMNS = [
    GEO_LAT_COLUMN,
    GEO_LON_COLUMN,
]
RUSSIA2021_CATEGORICAL_FEATURES = [
    "building_type",
    "object_type",
    "region",
]
RUSSIA2021_DERIVED_NUMERIC_FEATURES = [
    "is_studio",
    "area_per_room",
    "floor_ratio",
    "is_top_floor",
    "is_first_floor",
    "kitchen_ratio",
    "rooms_density",
    "has_coordinates",
]
RUSSIA2021_SOURCE_COLUMNS = (
    NEW_DATASET_REQUIRED_COLUMNS
    + RUSSIA2021_OPTIONAL_NUMERIC_COLUMNS
    + RUSSIA2021_SOURCE_COORDINATE_COLUMNS
    + RUSSIA2021_CATEGORICAL_FEATURES
)
RUSSIA2021_MODEL_NUMERIC_FEATURES = (
    RUSSIA2021_FEATURE_COLUMNS
    + RUSSIA2021_OPTIONAL_NUMERIC_COLUMNS
    + RUSSIA2021_DERIVED_NUMERIC_FEATURES
)
RUSSIA2021_MODEL_FEATURE_COLUMNS = (
    RUSSIA2021_MODEL_NUMERIC_FEATURES
    + RUSSIA2021_CATEGORICAL_FEATURES
)
RUSSIA2021_TARGET_COLUMN = PRICE_COLUMN
RUSSIA2021_DATASET_NAME = "daniilakk/Russia_Real_Estate_2021"

FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    TOTAL_AREA_COLUMN: (AREA_COLUMN,),
    AREA_COLUMN: (TOTAL_AREA_COLUMN,),
    KITCHEN_AREA_COLUMN: (NEW_KITCHEN_AREA_COLUMN,),
    NEW_KITCHEN_AREA_COLUMN: (KITCHEN_AREA_COLUMN,),
    FLOOR_COLUMN: (LEVEL_COLUMN,),
    LEVEL_COLUMN: (FLOOR_COLUMN,),
    TOTAL_FLOORS_COLUMN: (LEVELS_COLUMN,),
    LEVELS_COLUMN: (TOTAL_FLOORS_COLUMN,),
    LATITUDE_COLUMN: (GEO_LAT_COLUMN,),
    LONGITUDE_COLUMN: (GEO_LON_COLUMN,),
    PRICE_USD_COLUMN: (PRICE_COLUMN, LISTING_PRICE_COLUMN),
    PRICE_COLUMN: (PRICE_USD_COLUMN, LISTING_PRICE_COLUMN),
}

LISTING_TO_MODEL_FIELD_MAP: dict[str, str] = {
    "district": "district",
    "rooms": "rooms",
    FLOOR_COLUMN: "floor",
    LEVEL_COLUMN: "floor",
    TOTAL_FLOORS_COLUMN: "total_floors",
    LEVELS_COLUMN: "total_floors",
    TOTAL_AREA_COLUMN: "area",
    AREA_COLUMN: "area",
    "living_area_m2": "living_area_m2",
    KITCHEN_AREA_COLUMN: "kitchen_area_m2",
    NEW_KITCHEN_AREA_COLUMN: "kitchen_area_m2",
    "ceiling_height": "ceiling_height",
    "building_type": "building_type",
    "object_type": "object_type",
    "region": "region",
    "building_series": "building_series",
    "year_built": "year_built",
    "condition": "condition",
    "heating": "heating",
    "gas_supply": "gas_supply",
    "bathroom": "bathroom",
    "balcony": "balcony",
    "parking": "parking",
    "furniture": "furniture",
    "flooring": "flooring",
    "door_type": "door_type",
    "has_landline_phone": "has_landline_phone",
    "internet": "internet",
    "mortgage": "mortgage",
    "seller_type": "seller_type",
    "latitude": "latitude",
    "longitude": "longitude",
    "photo_count": "photo_count",
}


@dataclass
class FeatureConfig:
    target_column: str
    numerical_features: list[str]
    categorical_features: list[str]
    derived_numeric_features: list[str] = field(default_factory=list)
    excluded_columns: list[str] = field(default_factory=list)
    log_target: bool = True

    @property
    def feature_columns(self) -> list[str]:
        return self.numerical_features + self.categorical_features


def excluded_training_columns() -> list[str]:
    return [
        TARGET_COLUMN,
        PRICE_COLUMN,
        LISTING_PRICE_COLUMN,
    ] + LEAKAGE_COLUMNS + IRRELEVANT_COLUMNS + TEXT_LIKE_COLUMNS


def expected_columns_for_config(feature_config: FeatureConfig) -> set[str]:
    return set(feature_config.feature_columns)


def russia2021_feature_config() -> FeatureConfig:
    return FeatureConfig(
        target_column=RUSSIA2021_TARGET_COLUMN,
        numerical_features=list(RUSSIA2021_MODEL_NUMERIC_FEATURES),
        categorical_features=list(RUSSIA2021_CATEGORICAL_FEATURES),
        derived_numeric_features=list(RUSSIA2021_DERIVED_NUMERIC_FEATURES),
        excluded_columns=excluded_training_columns(),
        log_target=True,
    )
