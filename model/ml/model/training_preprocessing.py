from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from model.ml.model.feature_schema import (
    DERIVED_NUMERIC_FEATURES,
    REFERENCE_YEAR,
    TARGET_COLUMN,
    TOTAL_AREA_COLUMN,
    FeatureConfig,
    excluded_training_columns,
)
from model.ml.model.normalization import create_model_features, normalize_feature_frame


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = normalize_feature_frame(
        df,
        FeatureConfig(
            target_column=TARGET_COLUMN,
            numerical_features=[TOTAL_AREA_COLUMN],
            categorical_features=[],
            derived_numeric_features=[],
            excluded_columns=[],
        ),
    )

    if "listing_id" in cleaned.columns:
        cleaned = cleaned.drop_duplicates(subset=["listing_id"])

    cleaned = cleaned.dropna(subset=[TARGET_COLUMN, TOTAL_AREA_COLUMN], how="any")
    cleaned = cleaned[cleaned[TARGET_COLUMN] > 10000]
    cleaned = cleaned[cleaned[TOTAL_AREA_COLUMN] > 10]

    if "rooms" in cleaned.columns:
        rooms = pd.to_numeric(cleaned["rooms"], errors="coerce")
        cleaned = cleaned[(rooms.isna()) | (rooms == -1) | (rooms > 0)]
        rooms = pd.to_numeric(cleaned["rooms"], errors="coerce")
        cleaned = cleaned[(rooms.isna()) | (rooms <= 10)]

    if "year_built" in cleaned.columns:
        cleaned.loc[
            (cleaned["year_built"] < 1900) | (cleaned["year_built"] > REFERENCE_YEAR + 1),
            "year_built",
        ] = np.nan

    if {"latitude", "longitude"}.issubset(cleaned.columns):
        invalid_geo = ~(
            cleaned["latitude"].between(41.0, 44.0, inclusive="both")
            & cleaned["longitude"].between(73.0, 76.0, inclusive="both")
        )
        cleaned.loc[invalid_geo, ["latitude", "longitude"]] = np.nan

    return cleaned


def build_feature_config(df: pd.DataFrame) -> FeatureConfig:
    excluded_columns = excluded_training_columns()

    candidate_columns = [column for column in df.columns if column not in excluded_columns]
    numeric_columns = [
        column
        for column in candidate_columns
        if pd.api.types.is_numeric_dtype(df[column])
    ]
    categorical_columns = [
        column
        for column in candidate_columns
        if column not in numeric_columns
    ]

    return FeatureConfig(
        target_column=TARGET_COLUMN,
        numerical_features=list(dict.fromkeys(numeric_columns + DERIVED_NUMERIC_FEATURES)),
        categorical_features=categorical_columns,
        derived_numeric_features=DERIVED_NUMERIC_FEATURES,
        excluded_columns=excluded_columns,
        log_target=True,
    )


def prepare_training_frame(
    raw_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, FeatureConfig, dict[str, Any]]:
    cleaned_df = clean_dataset(raw_df)
    feature_config = build_feature_config(cleaned_df)
    feature_frame = create_model_features(cleaned_df, feature_config)
    target = cleaned_df[feature_config.target_column].astype(float)

    qc_summary = {
        "rows_before_cleaning": int(len(raw_df)),
        "rows_after_cleaning": int(len(cleaned_df)),
        "rows_removed": int(len(raw_df) - len(cleaned_df)),
        "target_skew_raw": float(target.skew()),
        "target_skew_log1p": float(np.log1p(target).skew()),
        "selected_numerical_features": feature_config.numerical_features,
        "selected_categorical_features": feature_config.categorical_features,
    }

    return feature_frame, target, feature_config, qc_summary
