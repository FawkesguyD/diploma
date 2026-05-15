"""Payload-модели очередей RabbitMQ модуля nlp-parser.

Контракты см. ``docs/design/messaging/README.md`` — секции
``parse.task.tg``, ``parse.task.news`` и ``nlp.analyze``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TriggeredBy = Literal["schedule", "manual", "backfill"]


class TelegramParseFilters(BaseModel):
    """Опциональные фильтры парсинга Telegram-канала."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    limit: int | None = Field(default=None, ge=1, le=1000, description="Максимум сообщений за раз.")


class ParseTelegramCommand(BaseModel):
    """Команда ``parse.task.tg`` — спарсить Telegram-канал."""

    model_config = ConfigDict(populate_by_name=True)

    source_id: UUID
    since: datetime | None = Field(
        default=None,
        description="Если не задано — берётся last_polled_at источника.",
    )
    limit: int | None = Field(default=None, ge=1, le=1000)
    triggered_by: TriggeredBy = "schedule"
    job_id: UUID | None = Field(
        default=None,
        description="ops.parser_jobs.id — для обновления статуса воркером.",
    )


class NewsParseFilters(BaseModel):
    """Опциональные фильтры парсинга новостного источника (RSS/HTML)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    limit: int | None = Field(default=None, ge=1, le=1000)


class ParseNewsCommand(BaseModel):
    """Команда ``parse.task.news`` — спарсить новостной/RSS/HTML источник."""

    model_config = ConfigDict(populate_by_name=True)

    source_id: UUID
    since: datetime | None = None
    triggered_by: TriggeredBy = "schedule"
    job_id: UUID | None = Field(
        default=None,
        description="ops.parser_jobs.id — для обновления статуса воркером.",
    )


class AnalyzeMessageCommand(BaseModel):
    """Команда ``nlp.analyze`` — прогнать сообщение через NLP-пайплайн."""

    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(..., description="Mongo ObjectId сообщения как hex-строка.")
    lang_hint: str | None = Field(default=None, description="Если парсер уже определил язык.")
    force: bool = Field(
        default=False,
        description="Переразобрать даже при наличии активной аннотации.",
    )


__all__ = [
    "TriggeredBy",
    "TelegramParseFilters",
    "ParseTelegramCommand",
    "NewsParseFilters",
    "ParseNewsCommand",
    "AnalyzeMessageCommand",
]
