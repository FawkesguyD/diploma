from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from model.ml.model.feature_schema import TARGET_COLUMN
from model.ml.model.utils import RAW_DATA_DIR, ensure_directory


HF_DATASET_NAME = "raimbekovm/bishkek-real-estate"
HF_LISTINGS_URL = (
    "https://huggingface.co/datasets/"
    f"{HF_DATASET_NAME}/resolve/main/listings.csv"
)
DEFAULT_LOCAL_DATASET_PATH = RAW_DATA_DIR / "listings.csv"


def download_dataset(
    destination_path: Path = DEFAULT_LOCAL_DATASET_PATH,
    source_url: str = HF_LISTINGS_URL,
    force: bool = False,
    chunk_size: int = 1024 * 1024,
) -> Path:
    ensure_directory(destination_path.parent)

    if destination_path.exists() and not force:
        return destination_path

    response = requests.get(source_url, stream=True, timeout=120)
    response.raise_for_status()

    with destination_path.open("wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)

    return destination_path


def load_dataset_frame(
    local_path: Path = DEFAULT_LOCAL_DATASET_PATH,
    force_download: bool = False,
) -> pd.DataFrame:
    dataset_path = download_dataset(local_path, force=force_download)
    return pd.read_csv(dataset_path)


def dataset_fingerprint(dataset_path: Path) -> str:
    hasher = hashlib.sha256()
    with dataset_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def summarize_dataset(df: pd.DataFrame) -> dict[str, Any]:
    target = TARGET_COLUMN
    summary: dict[str, Any] = {
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "columns": list(df.columns),
        "dtypes": {column: str(dtype) for column, dtype in df.dtypes.items()},
        "missing_pct": (
            df.isna().mean().sort_values(ascending=False).mul(100).round(2).to_dict()
        ),
        "duplicate_rows": int(df.duplicated().sum()),
    }

    if "listing_id" in df.columns:
        summary["duplicate_listing_id"] = int(df.duplicated(subset=["listing_id"]).sum())
    if "url" in df.columns:
        summary["duplicate_url"] = int(df.duplicated(subset=["url"]).sum())
    if target in df.columns:
        summary["target_summary"] = {
            key: float(value)
            for key, value in df[target]
            .describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
            .to_dict()
            .items()
        }

    return summary
