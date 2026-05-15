"""Общий конверт сообщений RabbitMQ / Kafka.

Соответствует разделу `Общие принципы` в
`docs/design/messaging/README.md`.

Поля:
- ``schema_version`` — версия контракта (минорные совместимые изменения — без подъёма).
- ``message_id`` — UUID, обязателен для идемпотентности (RabbitMQ at-least-once).
- ``correlation_id`` — UUID, пробрасывается через всю цепочку для трассировки.
- ``issued_at`` — момент публикации в UTC.
- ``payload`` — Pydantic-модель конкретного контракта (Generic).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "v1"

PayloadT = TypeVar("PayloadT", bound=BaseModel)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Envelope(BaseModel, Generic[PayloadT]):
    """Общий конверт для всех сообщений между сервисами."""

    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_timedelta="iso8601",
    )

    schema_version: str = Field(default=SCHEMA_VERSION)
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    issued_at: datetime = Field(default_factory=_utcnow)
    payload: PayloadT


__all__ = ["Envelope", "SCHEMA_VERSION", "PayloadT"]
