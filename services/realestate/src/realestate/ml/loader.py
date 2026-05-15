"""Загрузка артефакта модели из MinIO в локальную ФС.

Бандл — joblib-файл, формат описан в `model/ml/model/persistence.py`
(`LoadedModelBundle`).
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio

from realestate.config import Settings


@dataclass(slots=True)
class ModelArtifact:
    """Локальная ссылка на загруженный из MinIO артефакт + метаданные реестра."""

    local_path: Path
    minio_path: str
    version: str
    model_id: str  # UUID core.model_registry.id (как строка)


def _build_minio_client(settings: Settings) -> Minio:
    parsed = urlparse(settings.minio_endpoint)
    if not parsed.netloc:
        # endpoint вида "minio:9000" без схемы
        netloc = settings.minio_endpoint
        secure = settings.minio_secure
    else:
        netloc = parsed.netloc
        secure = parsed.scheme == "https" or settings.minio_secure
    return Minio(
        netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def download_model_artifact(
    settings: Settings,
    *,
    minio_path: str,
    version: str,
    model_id: str,
    cache_dir: Path | None = None,
) -> ModelArtifact:
    """Скачивает joblib-файл из MinIO.

    Если в `minio_path` указан суффикс файла — берём его. Иначе ищем
    `bundle.joblib` или первый `.joblib` в префиксе.
    """
    client = _build_minio_client(settings)
    bucket = settings.minio_bucket

    # Нормализуем путь: убираем ведущий "/" и имя бакета, если он там оказался.
    obj_key = minio_path.lstrip("/")
    if obj_key.startswith(f"{bucket}/"):
        obj_key = obj_key[len(bucket) + 1 :]

    if not obj_key.endswith(".joblib"):
        # это префикс — попробуем найти конкретный файл
        candidates = list(client.list_objects(bucket, prefix=obj_key.rstrip("/") + "/", recursive=True))
        joblib_objects = [c for c in candidates if c.object_name.endswith(".joblib")]
        if not joblib_objects:
            raise FileNotFoundError(
                f"В MinIO {bucket}/{obj_key} нет .joblib артефактов модели."
            )
        # bundle.joblib приоритетнее
        chosen = next(
            (c for c in joblib_objects if c.object_name.endswith("bundle.joblib")),
            joblib_objects[0],
        )
        obj_key = chosen.object_name

    cache_root = Path(cache_dir or os.getenv("MODEL_CACHE_DIR") or tempfile.gettempdir()) / "realestate-models"
    cache_root.mkdir(parents=True, exist_ok=True)
    local_path = cache_root / f"{version}_{Path(obj_key).name}"

    if not local_path.exists():
        client.fget_object(bucket, obj_key, str(local_path))

    return ModelArtifact(local_path=local_path, minio_path=obj_key, version=version, model_id=model_id)


__all__ = ["ModelArtifact", "download_model_artifact"]
