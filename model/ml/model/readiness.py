from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model.ml.model.persistence import LoadedModelBundle, load_model_bundle
from model.ml.model.utils import ARTIFACTS_DIR, save_json, utc_now_iso


READINESS_MANIFEST_NAME = "model_readiness.json"
READY_STATUSES = {"ready", "active"}


class ModelReadinessError(RuntimeError):
    pass


def default_readiness_manifest_path(artifacts_dir: Path = ARTIFACTS_DIR) -> Path:
    return artifacts_dir / READINESS_MANIFEST_NAME


def load_readiness_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or default_readiness_manifest_path()
    if not manifest_path.exists():
        raise ModelReadinessError(f"Readiness manifest not found: {manifest_path}")
    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, ValueError) as exc:
        raise ModelReadinessError(f"Cannot read readiness manifest: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ModelReadinessError("Readiness manifest must be a JSON object.")
    return payload


def save_readiness_manifest(
    *,
    artifact_path: Path,
    model_name: str,
    metrics: dict[str, Any],
    metadata: dict[str, Any],
    candidates: list[dict[str, Any]] | None = None,
    status: str = "active",
    output_path: Path | None = None,
) -> Path:
    manifest_path = output_path or default_readiness_manifest_path(artifact_path.parent)
    payload = {
        "schema_version": 1,
        "status": status,
        "active_model_path": str(artifact_path),
        "active_model_name": model_name,
        "base_currency": "RUB",
        "created_at": utc_now_iso(),
        "metrics": metrics,
        "metadata": metadata,
        "market_bounds": metadata.get("market_bounds"),
        "candidates": candidates or [],
        "readiness_checks": {
            "base_currency_rub": True,
            "artifact_exists": artifact_path.exists(),
            "validation_passed": status in READY_STATUSES,
        },
    }
    save_json(payload, manifest_path)
    return manifest_path


def resolve_ready_model_path(
    *,
    configured_model_path: Path,
    manifest_path: Path | None = None,
    model_path_is_explicit: bool = False,
) -> tuple[Path, dict[str, Any]]:
    manifest = load_readiness_manifest(manifest_path)
    status = str(manifest.get("status") or "").lower()
    if status not in READY_STATUSES:
        raise ModelReadinessError(f"Active model is not ready: status={status or 'missing'}")

    active_model_path = manifest.get("active_model_path")
    if not active_model_path:
        raise ModelReadinessError("Readiness manifest does not define active_model_path.")

    resolved_path = Path(active_model_path)
    if not resolved_path.is_absolute():
        resolved_path = (manifest_path or default_readiness_manifest_path()).parent / resolved_path

    if model_path_is_explicit:
        resolved_configured = configured_model_path
        if not resolved_configured.is_absolute():
            resolved_configured = Path.cwd() / resolved_configured
        if resolved_configured.resolve() != resolved_path.resolve():
            raise ModelReadinessError(
                "MODEL_PATH points to a model that is not active in readiness manifest."
            )

    if not resolved_path.exists():
        raise ModelReadinessError(f"Ready model artifact not found: {resolved_path}")

    return resolved_path, manifest


def load_ready_model_bundle(
    *,
    configured_model_path: Path,
    manifest_path: Path | None = None,
    model_path_is_explicit: bool = False,
) -> LoadedModelBundle:
    model_path, manifest = resolve_ready_model_path(
        configured_model_path=configured_model_path,
        manifest_path=manifest_path,
        model_path_is_explicit=model_path_is_explicit,
    )
    bundle = load_model_bundle(model_path)
    if bundle.base_currency != "RUB":
        raise ModelReadinessError("Active model must use RUB as base currency.")

    manifest_metadata = manifest.get("metadata") or {}
    bundle.metadata = {
        **(bundle.metadata or {}),
        **manifest_metadata,
    }
    if manifest.get("market_bounds") and "market_bounds" not in bundle.metadata:
        bundle.metadata["market_bounds"] = manifest["market_bounds"]
    bundle.metadata["readiness"] = {
        "status": manifest.get("status"),
        "active_model_path": str(model_path),
        "active_model_name": manifest.get("active_model_name"),
        "created_at": manifest.get("created_at"),
    }
    return bundle
