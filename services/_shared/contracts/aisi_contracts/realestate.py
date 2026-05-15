"""Payload-модели очередей RabbitMQ модуля realestate.

Контракты см. `docs/design/messaging/README.md` секции
``realestate.score`` и ``realestate.rank``.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScoreCommand(BaseModel):
    """Команда `realestate.score` — оценить объект (или батч)."""

    model_config = ConfigDict(populate_by_name=True)

    object_ids: list[str] = Field(..., min_length=1, description="Mongo ObjectId как hex-строки.")
    model_version: str | None = Field(
        default=None,
        description="Если не задано — берётся активная версия из core.model_registry.",
    )
    force: bool = Field(default=False, description="Переоценить даже если уже есть актуальная аннотация.")


class RankScope(BaseModel):
    """Скоуп ранжирования — что именно пересчитывать."""

    city: str | None = None
    district_slug: str | None = None
    since: str | None = Field(
        default=None,
        description="ISO-8601 UTC; если задан — учитывать оценки начиная с этого момента.",
    )


class RankCommand(BaseModel):
    """Команда `realestate.rank` — пересчитать ранжирование оценок одного запуска."""

    model_config = ConfigDict(populate_by_name=True)

    model_run_id: UUID
    scope: RankScope = Field(default_factory=RankScope)


class ScoreResult(BaseModel):
    """Результат инференса по одному объекту (внутренний обмен в worker'е)."""

    object_id: str
    predicted_price: float
    listing_price: float | None
    deviation_abs: float | None
    deviation_pct: float | None
    is_undervalued: bool
    confidence: Literal["low", "medium", "high"] = "high"
    model_version: str
    model_run_id: UUID
    features_used: dict


class RealestateParseFilters(BaseModel):
    """Опциональные фильтры для парсинга площадки недвижимости.

    Соответствует разделу ``parse.task.realestate`` в
    ``docs/design/messaging/README.md``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    city: str | None = None
    rooms: list[int] | None = None
    price_max: int | None = Field(default=None, ge=0)


class ParseRealestateCommand(BaseModel):
    """Команда ``parse.task.realestate`` — спарсить площадку с объявлениями."""

    model_config = ConfigDict(populate_by_name=True)

    source_id: UUID
    filters: RealestateParseFilters | None = None
    triggered_by: Literal["schedule", "manual", "backfill"] = "schedule"


__all__ = [
    "ScoreCommand",
    "RankCommand",
    "RankScope",
    "ScoreResult",
    "ParseRealestateCommand",
    "RealestateParseFilters",
]
