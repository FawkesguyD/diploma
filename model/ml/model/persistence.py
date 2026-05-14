from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np

from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.feature_schema import DEFAULT_ARTIFACT_BASE_CURRENCY
from model.ml.model.utils import ensure_directory, utc_now_iso


ARTIFACT_SCHEMA_VERSION = 2
TARGET_TRANSFORM_IDENTITY = "identity"
TARGET_TRANSFORM_LOG1P = "log1p"
TARGET_TRANSFORM_LOG = "log"
TargetTransform = Literal["identity", "log1p", "log"]


@dataclass
class LoadedModelBundle:
    model_name: str
    model: Any
    feature_config: FeatureConfig
    metrics: dict[str, Any]
    target_column: str
    log_target: bool
    target_transform: TargetTransform | None = None
    artifact_schema_version: int = 1
    base_currency: str = DEFAULT_ARTIFACT_BASE_CURRENCY
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.target_transform is None:
            self.target_transform = (
                TARGET_TRANSFORM_LOG1P if self.log_target else TARGET_TRANSFORM_IDENTITY
            )
        self.base_currency = (self.base_currency or DEFAULT_ARTIFACT_BASE_CURRENCY).upper()
        if self.metadata is None:
            self.metadata = {}


def resolve_target_transform(payload: dict[str, Any]) -> TargetTransform:
    transform = payload.get("target_transform")
    if transform in {TARGET_TRANSFORM_IDENTITY, TARGET_TRANSFORM_LOG1P, TARGET_TRANSFORM_LOG}:
        return transform
    return TARGET_TRANSFORM_LOG1P if payload.get("log_target") else TARGET_TRANSFORM_IDENTITY


def inverse_transform_predictions(
    predictions: Any,
    target_transform: TargetTransform,
) -> np.ndarray:
    prediction_array = np.asarray(predictions, dtype=float)
    if target_transform == TARGET_TRANSFORM_LOG1P:
        return np.expm1(prediction_array)
    if target_transform == TARGET_TRANSFORM_LOG:
        return np.exp(prediction_array)
    return prediction_array


def load_model_bundle(model_path: str | Path) -> LoadedModelBundle:
    payload = joblib.load(model_path)
    feature_config = FeatureConfig(**payload["feature_config"])
    target_transform = resolve_target_transform(payload)
    return LoadedModelBundle(
        model_name=payload["model_name"],
        model=payload["model"],
        feature_config=feature_config,
        metrics=payload["metrics"],
        target_column=payload.get("target_column", feature_config.target_column),
        log_target=bool(payload.get("log_target", target_transform != TARGET_TRANSFORM_IDENTITY)),
        target_transform=target_transform,
        artifact_schema_version=int(payload.get("artifact_schema_version", 1)),
        base_currency=payload.get("base_currency", DEFAULT_ARTIFACT_BASE_CURRENCY),
        metadata=payload.get("metadata", {}),
    )


def save_model_bundle(
    model: Any,
    model_name: str,
    feature_config: FeatureConfig,
    metrics: dict[str, Any],
    output_path: Path,
    target_transform: TargetTransform | None = None,
    base_currency: str = DEFAULT_ARTIFACT_BASE_CURRENCY,
    metadata: dict[str, Any] | None = None,
) -> Path:
    ensure_directory(output_path.parent)
    resolved_target_transform: TargetTransform = target_transform or (
        TARGET_TRANSFORM_LOG1P if feature_config.log_target else TARGET_TRANSFORM_IDENTITY
    )

    bundle = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_name": model_name,
        "model": model,
        "feature_config": asdict(feature_config),
        "metrics": metrics,
        "created_at": utc_now_iso(),
        "target_column": feature_config.target_column,
        "log_target": feature_config.log_target,
        "target_transform": resolved_target_transform,
        "base_currency": base_currency.upper(),
        "metadata": metadata or {},
    }

    joblib.dump(bundle, output_path)
    return output_path
