from __future__ import annotations

from typing import Any

import pandas as pd

from model.ml.model.feature_schema import FeatureConfig
from model.ml.model.normalization import create_model_features, prepare_objects_frame


def prepare_inference_frame(
    objects: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
    feature_config: FeatureConfig,
) -> pd.DataFrame:
    frame = prepare_objects_frame(objects)
    return create_model_features(frame, feature_config)
