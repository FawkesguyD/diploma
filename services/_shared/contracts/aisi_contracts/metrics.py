"""Payload-модели Kafka-метрик.

Топики и контракты — `docs/design/messaging/README.md` секция «Kafka».

* `PriceMetric`   — топик `metrics.prices`,   продьюсер `realestate`.
* `MessageMetric` — топик `metrics.messages`, продьюсер `nlp-parser`.

Поля повторяют ClickHouse-схемы `events_prices` / `events_messages`
(`docs/design/databases/clickhouse.md`) — денормализованные slug-и,
чтобы консьюмер `metrics` мог вставлять строки 1-в-1 без джойнов.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PriceMetric(BaseModel):
    """Один Kafka-message в `metrics.prices` ↔ одна строка в ClickHouse `events_prices`."""

    model_config = ConfigDict(populate_by_name=True)

    event_time: datetime = Field(..., description="Момент инференса (UTC).")
    published_at: datetime = Field(..., description="Когда объект был опубликован на площадке.")

    object_id: str = Field(..., description="Mongo ObjectId как hex-строка (ключ партиционирования).")
    source_id: UUID
    object_kind: Literal["residential", "commercial", "land", "parking"]
    channel_site: str
    city: str | None = None
    district_slug: str | None = None

    rooms: int | None = None
    area: float | None = None
    floor: int | None = None
    year_built: int | None = None

    price_real: float | None = None
    price_predicted: float
    deviation_abs: float | None = None
    deviation_pct: float | None = None
    is_undervalued: bool
    rank_in_run: int | None = None

    model_version: str
    model_run_id: UUID


class MessageMetric(BaseModel):
    """Один Kafka-message в `metrics.messages` ↔ одна строка в ClickHouse `events_messages`.

    Поля повторяют схему таблицы `events_messages`
    (`docs/design/databases/clickhouse.md`). Источник правды для текстов
    самого сообщения — Mongo (`messages._id`), здесь только аннотация.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_time: datetime = Field(..., description="Момент NLP-обработки (UTC).")
    published_at: datetime = Field(..., description="Когда сообщение было опубликовано в источнике.")

    message_id: str = Field(..., description="Mongo ObjectId сообщения (hex-строка).")
    source_id: UUID
    channel_kind: Literal["tg", "news", "rss", "html"]
    channel_site: str

    topic_slug: str = Field(..., description="Топ-1 тема от классификатора.")
    topic_score: float = Field(..., ge=0.0, le=1.0)
    topics_all: list[str] = Field(default_factory=list, description="Все темы (для co-occurrence).")

    sentiment_label: Literal["positive", "neutral", "negative"]
    sentiment_score: float

    is_ad: bool
    lang: str = Field(default="ru")

    entities_districts: list[str] = Field(
        default_factory=list, description="Slug-и упомянутых районов."
    )
    entities_developers: list[str] = Field(
        default_factory=list, description="Имена застройщиков как они извлечены NER."
    )

    model_run_id: UUID


__all__ = ["PriceMetric", "MessageMetric"]
