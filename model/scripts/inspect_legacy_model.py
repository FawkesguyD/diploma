from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from model.ml.model.feature_schema import DEFAULT_ARTIFACT_BASE_CURRENCY
from model.ml.model.persistence import TARGET_TRANSFORM_LOG1P, resolve_target_transform
from model.ml.model.utils import PROJECT_ROOT, ensure_directory, to_serializable


DEFAULT_PRIMARY_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "best_model.joblib"
DEFAULT_FALLBACK_MODEL_PATH = PROJECT_ROOT / "ml" / "artifacts" / "catboost_regressor.joblib"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "reports" / "legacy_model_summary.json"


def model_type_name(model: Any) -> str:
    cls = model.__class__
    return f"{cls.__module__}.{cls.__name__}"


def is_catboost_model(model: Any) -> bool:
    return model_type_name(model).startswith("catboost.")


def load_payload(path: Path) -> Any:
    return joblib.load(path)


def choose_legacy_payload(primary_path: Path, fallback_path: Path) -> tuple[Path, Any, bool]:
    primary_payload = load_payload(primary_path)
    primary_model = primary_payload.get("model") if isinstance(primary_payload, dict) else primary_payload
    if is_catboost_model(primary_model):
        return primary_path, primary_payload, False

    fallback_payload = load_payload(fallback_path)
    fallback_model = fallback_payload.get("model") if isinstance(fallback_payload, dict) else fallback_payload
    if not is_catboost_model(fallback_model):
        raise TypeError(
            "Neither best_model.joblib nor catboost_regressor.joblib contains a CatBoost model."
        )
    return fallback_path, fallback_payload, True


def catboost_params(model: Any) -> dict[str, Any]:
    if not hasattr(model, "get_all_params"):
        return {}
    params = model.get_all_params()
    selected_keys = [
        "learning_rate",
        "depth",
        "iterations",
        "loss_function",
        "eval_metric",
        "l2_leaf_reg",
        "random_seed",
        "use_best_model",
        "od_wait",
        "bootstrap_type",
        "rsm",
    ]
    result = {key: params.get(key) for key in selected_keys if key in params}
    result["tree_count_"] = getattr(model, "tree_count_", None)
    return result


def build_summary(primary_path: Path, fallback_path: Path) -> dict[str, Any]:
    artifact_path, payload, used_fallback = choose_legacy_payload(primary_path, fallback_path)
    bundle_type = type(payload).__name__
    bundle_keys = list(payload.keys()) if isinstance(payload, dict) else []
    model = payload.get("model") if isinstance(payload, dict) else payload
    feature_config = payload.get("feature_config", {}) if isinstance(payload, dict) else {}
    target_transform = resolve_target_transform(payload) if isinstance(payload, dict) else "identity"
    target_currency = (payload.get("base_currency") if isinstance(payload, dict) else None) or DEFAULT_ARTIFACT_BASE_CURRENCY

    numerical_features = list(feature_config.get("numerical_features", []))
    categorical_features = list(feature_config.get("categorical_features", []))
    derived_numeric_features = list(feature_config.get("derived_numeric_features", []))

    return {
        "artifact_path": str(artifact_path),
        "primary_artifact_path": str(primary_path),
        "fallback_artifact_path": str(fallback_path),
        "used_fallback_artifact": used_fallback,
        "bundle_type": bundle_type,
        "bundle_keys": bundle_keys,
        "model_name": payload.get("model_name") if isinstance(payload, dict) else None,
        "model_type": model_type_name(model),
        "target_column": (
            payload.get("target_column") if isinstance(payload, dict) else None
        ) or feature_config.get("target_column"),
        "target_currency": str(target_currency).upper(),
        "log_target": bool(payload.get("log_target", target_transform == TARGET_TRANSFORM_LOG1P))
        if isinstance(payload, dict)
        else False,
        "target_transform": target_transform,
        "inverse_transform": "expm1" if target_transform == "log1p" else "exp" if target_transform == "log" else "identity",
        "numerical_features": numerical_features,
        "categorical_features": categorical_features,
        "derived_numeric_features": derived_numeric_features,
        "excluded_columns": list(feature_config.get("excluded_columns", [])),
        "catboost_params": catboost_params(model),
        "artifact_metrics": payload.get("metrics", {}) if isinstance(payload, dict) else {},
        "total_feature_count": len(numerical_features) + len(categorical_features),
    }


def save_summary(summary: dict[str, Any], output_path: Path) -> None:
    ensure_directory(output_path.parent)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(to_serializable(summary), file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect legacy model artifact without modifying it.")
    parser.add_argument("--primary-model-path", type=Path, default=DEFAULT_PRIMARY_MODEL_PATH)
    parser.add_argument("--fallback-model-path", type=Path, default=DEFAULT_FALLBACK_MODEL_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_summary(args.primary_model_path, args.fallback_model_path)
    save_summary(summary, args.output_path)
    print(f"Saved legacy model summary: {args.output_path}")


if __name__ == "__main__":
    main()
