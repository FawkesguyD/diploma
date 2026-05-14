from __future__ import annotations

from model.ml.model.utils import ARTIFACTS_DIR, DATA_DIR, ML_ROOT, MODEL_DIR, PROJECT_ROOT, RANDOM_STATE, RAW_DATA_DIR, REPORTS_DIR


DEFAULT_MODEL_ARTIFACT_PATH = ARTIFACTS_DIR / "best_model_russia2021.joblib"

__all__ = [
    "ARTIFACTS_DIR",
    "DATA_DIR",
    "ML_ROOT",
    "MODEL_DIR",
    "PROJECT_ROOT",
    "RANDOM_STATE",
    "RAW_DATA_DIR",
    "REPORTS_DIR",
    "DEFAULT_MODEL_ARTIFACT_PATH",
]
