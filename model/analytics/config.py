from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model.ml.model.utils import ARTIFACTS_DIR, PROJECT_ROOT
from model.shared.db.session import get_database_url


ANALYTICS_ROOT = PROJECT_ROOT / "analytics"
DEFAULT_OUTPUT_DIR = ANALYTICS_ROOT / "outputs"
DEFAULT_REPORTS_DIR = ANALYTICS_ROOT / "reports"
DEFAULT_READINESS_PATH = ARTIFACTS_DIR / "model_readiness.json"
DEFAULT_MODEL_PATH = ARTIFACTS_DIR / "best_model_russia2021.joblib"
LEGACY_MODEL_PATH = ARTIFACTS_DIR / "best_model.joblib"
DEFAULT_MAX_ROWS = 200_000
DEFAULT_EVAL_MAX_ROWS = 5_000
DEFAULT_TOP_DISTRICTS = 20
DEFAULT_RANDOM_STATE = 42
DEFAULT_GEOCODE_LIMIT = 100
DEFAULT_CONTROL_SAMPLE_SIZE = 1_000
DEFAULT_CONTROL_SAMPLE_SEED = 42


def _optional_int(value: str | None, default: int | None) -> int | None:
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"none", "null", "all"}:
        return None
    return int(normalized)


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_model_path() -> Path:
    configured = os.getenv("MODEL_PATH")
    if configured:
        return Path(configured)
    if DEFAULT_MODEL_PATH.exists():
        return DEFAULT_MODEL_PATH
    return LEGACY_MODEL_PATH


@dataclass(frozen=True)
class AnalyticsConfig:
    database_url: str
    output_dir: Path = DEFAULT_OUTPUT_DIR
    reports_dir: Path = DEFAULT_REPORTS_DIR
    max_rows: int | None = DEFAULT_MAX_ROWS
    eval_max_rows: int = DEFAULT_EVAL_MAX_ROWS
    top_districts: int = DEFAULT_TOP_DISTRICTS
    random_state: int = DEFAULT_RANDOM_STATE
    control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE
    control_sample_seed: int = DEFAULT_CONTROL_SAMPLE_SEED
    model_path: Path = DEFAULT_MODEL_PATH
    readiness_path: Path = DEFAULT_READINESS_PATH
    model_path_is_explicit: bool = False
    enable_reverse_geocoding: bool = False
    geocode_limit: int = DEFAULT_GEOCODE_LIMIT

    @classmethod
    def from_env(cls) -> "AnalyticsConfig":
        return cls(
            database_url=os.getenv("DATABASE_URL") or get_database_url(),
            output_dir=Path(os.getenv("ANALYTICS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))),
            reports_dir=Path(os.getenv("ANALYTICS_REPORTS_DIR", str(DEFAULT_REPORTS_DIR))),
            max_rows=_optional_int(os.getenv("ANALYTICS_MAX_ROWS"), DEFAULT_MAX_ROWS),
            eval_max_rows=int(os.getenv("ANALYTICS_EVAL_MAX_ROWS", str(DEFAULT_EVAL_MAX_ROWS))),
            top_districts=int(os.getenv("ANALYTICS_TOP_DISTRICTS", str(DEFAULT_TOP_DISTRICTS))),
            random_state=int(os.getenv("ANALYTICS_RANDOM_STATE", str(DEFAULT_RANDOM_STATE))),
            control_sample_size=int(os.getenv("ANALYTICS_CONTROL_SAMPLE_SIZE", str(DEFAULT_CONTROL_SAMPLE_SIZE))),
            control_sample_seed=int(os.getenv("ANALYTICS_CONTROL_SAMPLE_SEED", str(DEFAULT_CONTROL_SAMPLE_SEED))),
            model_path=_default_model_path(),
            readiness_path=Path(os.getenv("MODEL_READINESS_PATH", str(DEFAULT_READINESS_PATH))),
            model_path_is_explicit=os.getenv("MODEL_PATH") is not None,
            enable_reverse_geocoding=_bool_from_env(os.getenv("ANALYTICS_ENABLE_REVERSE_GEOCODING")),
            geocode_limit=int(os.getenv("ANALYTICS_GEOCODE_LIMIT", str(DEFAULT_GEOCODE_LIMIT))),
        )
