"""Тонкая обёртка над инференс-пайплайном из `model/ml/model/inference.py`.

Сама модель и фичеинжиниринг — это «source of truth» статьи и не дублируется
здесь. Мы только:

1. готовим dict с фичами из документа Mongo `objects`;
2. вызываем `predict_proxy_valuation_from_bundle`;
3. пересобираем результат в формат annotated_objects / Kafka.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

# Импорты из научного кода — в Dockerfile эта папка кладётся под /app/vendor/model/ml.
# Locally: добавить корень репо в PYTHONPATH или editable-install пакета model.
# Импорт ленивый чтобы сам модуль импортировался без model в окружении.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.ml.model.persistence import LoadedModelBundle

from realestate.ml.loader import ModelArtifact


OBJECT_TYPE_FALLBACK: dict[str, str] = {
    "residential": "secondary",
    "secondary": "secondary",
    "new": "new",
    "newbuilding": "new",
    "new_building": "new",
}


REGION_BY_CITY: dict[str, str] = {
    "moscow": "3",
    "москва": "3",
    "saint-petersburg": "2661",
    "st-petersburg": "2661",
    "санкт-петербург": "2661",
    "spb": "2661",
}


# Доля площади кухни в общей площади (среднее по Russia2021).
_DEFAULT_KITCHEN_RATIO = 0.18
_DEFAULT_BUILDING_TYPE = "monolith"


@dataclass(slots=True)
class PredictionResult:
    predicted_price: float
    price_per_m2: float | None
    listing_price: float | None
    delta_abs: float | None
    delta_pct: float | None
    is_undervalued: bool
    confidence: str
    features_used: dict[str, Any]
    warnings: list[str]


class ModelHolder:
    """Хранит активный bundle в памяти процесса (горячий swap при reload)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bundle: "LoadedModelBundle | None" = None
        self._artifact: ModelArtifact | None = None

    def load(self, artifact: ModelArtifact) -> None:
        from model.ml.model.persistence import load_model_bundle  # lazy
        bundle = load_model_bundle(artifact.local_path)
        with self._lock:
            self._bundle = bundle
            self._artifact = artifact

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._bundle is not None

    @property
    def artifact(self) -> ModelArtifact | None:
        with self._lock:
            return self._artifact

    @property
    def bundle(self) -> "LoadedModelBundle":
        with self._lock:
            if self._bundle is None:
                raise RuntimeError("Модель не загружена — вызовите ModelHolder.load() при старте.")
            return self._bundle


def object_to_features(object_doc: dict[str, Any]) -> dict[str, Any]:
    listing = object_doc.get("listing") or {}
    address = listing.get("address") or {}
    raw_object_type = object_doc.get("object_kind") or "residential"
    object_type = OBJECT_TYPE_FALLBACK.get(str(raw_object_type).lower(), "secondary")
    region_value = address.get("region") or REGION_BY_CITY.get(
        str(address.get("city") or "").lower(), "3"
    )
    area = listing.get("area")
    kitchen_area = listing.get("kitchen_area")
    if kitchen_area is None and isinstance(area, (int, float)):
        kitchen_area = round(float(area) * _DEFAULT_KITCHEN_RATIO, 2)
    building_type = listing.get("building_type") or _DEFAULT_BUILDING_TYPE
    return {
        "listing_id": str(object_doc.get("_id", "")),
        "listing_currency": listing.get("currency") or "RUB",
        "listing_price": listing.get("price"),
        "total_price": listing.get("price"),
        "area": area,
        "total_area_m2": area,
        "kitchen_area": kitchen_area,
        "rooms": listing.get("rooms"),
        "floor": listing.get("floor"),
        "level": listing.get("floor"),
        "total_floors": listing.get("total_floors"),
        "levels": listing.get("total_floors"),
        "year_built": listing.get("year_built"),
        "building_type": building_type,
        "object_type": object_type,
        "region": region_value,
        "district": address.get("district_slug"),
        "latitude": address.get("lat"),
        "longitude": address.get("lon"),
    }


def predict(holder: ModelHolder, object_doc: dict[str, Any]) -> PredictionResult:
    from model.ml.model.inference import predict_proxy_valuation_from_bundle  # lazy
    features = object_to_features(object_doc)
    response = predict_proxy_valuation_from_bundle(features, holder.bundle, include_explanation=False)
    predicted = float(response["predicted_price_rub"])
    listing_price = response.get("listing_price_rub")
    delta_abs = response.get("delta_abs_rub")
    delta_pct = response.get("delta_pct")
    # В научной модели delta = predicted - listing; в нашем контракте deviation
    # = listing - predicted (отрицательное = недооценка). Пересчитываем.
    deviation_abs = None
    deviation_pct = None
    if listing_price is not None and delta_abs is not None:
        deviation_abs = listing_price - predicted
        if listing_price != 0:
            deviation_pct = round(deviation_abs / listing_price * 100.0, 4)
    is_undervalued = bool(deviation_pct is not None and deviation_pct < -5.0)
    return PredictionResult(
        predicted_price=predicted,
        price_per_m2=response.get("price_per_m2_rub"),
        listing_price=listing_price,
        delta_abs=deviation_abs,
        delta_pct=deviation_pct,
        is_undervalued=is_undervalued,
        confidence=str(response.get("confidence", "high")),
        features_used=features,
        warnings=list(response.get("warnings", [])),
    )


__all__ = ["ModelHolder", "PredictionResult", "predict", "object_to_features"]
