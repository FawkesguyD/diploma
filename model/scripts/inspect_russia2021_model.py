from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import joblib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.ml.model.feature_schema import RUSSIA2021_BASE_CURRENCY
from model.scripts.russia2021_analysis_common import (
    DEFAULT_MODEL_PATH,
    DEFAULT_REPORTS_DIR,
    catboost_all_params_subset,
    catboost_params_from_model,
    load_russia2021_bundle,
    save_json,
    to_jsonable,
)


DEFAULT_OUTPUT_PATH = DEFAULT_REPORTS_DIR / "russia2021_model_summary.json"


def inspect_model(model_path: Path) -> dict[str, Any]:
    payload = joblib.load(model_path)
    bundle = load_russia2021_bundle(model_path)
    model = bundle.model
    feature_config = bundle.feature_config
    metadata = bundle.metadata or {}

    summary = {
        "artifact_path": str(model_path),
        "artifact_exists": model_path.exists(),
        "bundle_type": f"{type(payload).__module__}.{type(payload).__qualname__}",
        "bundle_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "artifact_schema_version": bundle.artifact_schema_version,
        "model_name": bundle.model_name,
        "model_type": f"{type(model).__module__}.{type(model).__qualname__}",
        "target_column": bundle.target_column,
        "log_target": bundle.log_target,
        "target_transform": bundle.target_transform,
        "inverse_transform": "exp" if bundle.target_transform == "log" else "expm1" if bundle.target_transform == "log1p" else "identity",
        "base_currency": bundle.base_currency,
        "target_currency": metadata.get("base_currency") or bundle.base_currency or RUSSIA2021_BASE_CURRENCY,
        "numerical_features": feature_config.numerical_features,
        "categorical_features": feature_config.categorical_features,
        "derived_numeric_features": feature_config.derived_numeric_features,
        "excluded_columns": feature_config.excluded_columns,
        "feature_count": len(feature_config.feature_columns),
        "catboost_params": catboost_params_from_model(model),
        "catboost_all_params_subset": catboost_all_params_subset(model),
        "metrics_in_artifact": bundle.metrics,
        "metadata": metadata,
        "notes": {
            "artifact_not_modified": True,
            "source": "joblib artifact inspection plus ml.model.persistence.load_model_bundle",
        },
    }
    return to_jsonable(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only inspection for best_model_russia2021.joblib.")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = inspect_model(args.model_path)
    save_json(summary, args.output_path)
    print(f"Saved model summary: {args.output_path}")


if __name__ == "__main__":
    main()
