from __future__ import annotations

import os
from pathlib import Path

from model.ml.model.feature_schema import DERIVED_NUMERIC_FEATURES, RUSSIA2021_DERIVED_NUMERIC_FEATURES
from model.ml.model.utils import ARTIFACTS_DIR


SERVICE_NAME = "real-estate-analytics-service"
DEFAULT_CURRENCY = "RUB"

MODEL_PATH_ENV = os.getenv("ANALYTICS_MODEL_PATH") or os.getenv("MODEL_PATH")
DEFAULT_MODEL_PATH = Path(MODEL_PATH_ENV or ARTIFACTS_DIR / "best_model_russia2021.joblib")
MODEL_READINESS_PATH = Path(
    os.getenv(
        "ANALYTICS_MODEL_READINESS_PATH",
        os.getenv("MODEL_READINESS_PATH", str(ARTIFACTS_DIR / "model_readiness.json")),
    )
)

ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "area": ("total_area_m2",),
    "kitchen_area": ("kitchen_area_m2",),
    "level": ("floor",),
    "levels": ("total_floors",),
    "latitude": ("geo_lat",),
    "longitude": ("geo_lon",),
    "listing_price": ("price", "price_usd"),
}

REJECTED_DERIVED_FIELDS = set(DERIVED_NUMERIC_FEATURES) | set(RUSSIA2021_DERIVED_NUMERIC_FEATURES) | {
    "expected_price_proxy",
    "delta_abs",
    "delta_pct",
    "price_per_m2",
    "price_per_m2_rub",
    "score",
}

FORMULA_BASELINE_COEFFICIENTS: dict[str, float] = {
    "intercept": 650_000.0,
    "area": 145_000.0,
    "kitchen_area": 25_000.0,
    "rooms": 250_000.0,
    "level": 35_000.0,
    "levels": 15_000.0,
}

FORMULA_BASELINE_NOTE = (
    "Временная formula baseline для MVP: эвристическая proxy valuation по доступным полям объявления."
)

