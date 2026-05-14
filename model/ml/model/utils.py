from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_DIR = Path(__file__).resolve().parent
ML_ROOT = MODEL_DIR.parent
PROJECT_ROOT = ML_ROOT.parent
DATA_DIR = ML_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
ARTIFACTS_DIR = ML_ROOT / "artifacts"
REPORTS_DIR = ML_ROOT / "reports"

RANDOM_STATE = 42


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_project_dirs() -> dict[str, Path]:
    return {
        "data": ensure_directory(DATA_DIR),
        "raw_data": ensure_directory(RAW_DATA_DIR),
        "artifacts": ensure_directory(ARTIFACTS_DIR),
        "reports": ensure_directory(REPORTS_DIR),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_serializable(item) for key, item in asdict(value).items()}

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_serializable(item) for item in value]

    return value


def save_json(payload: dict[str, Any], output_path: Path) -> None:
    ensure_directory(output_path.parent)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(to_serializable(payload), file, ensure_ascii=False, indent=2)
