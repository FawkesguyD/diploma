"""Общие контракты сообщений между сервисами АИС."""

from aisi_contracts.envelope import Envelope, SCHEMA_VERSION
from aisi_contracts.messages import (
    AnalyzeMessageCommand,
    NewsParseFilters,
    ParseNewsCommand,
    ParseTelegramCommand,
    TelegramParseFilters,
    TriggeredBy,
)
from aisi_contracts.metrics import MessageMetric, PriceMetric
from aisi_contracts.realestate import (
    ParseRealestateCommand,
    RankCommand,
    RankScope,
    RealestateParseFilters,
    ScoreCommand,
    ScoreResult,
)

__all__ = [
    "Envelope",
    "SCHEMA_VERSION",
    "ScoreCommand",
    "RankCommand",
    "RankScope",
    "ScoreResult",
    "ParseRealestateCommand",
    "RealestateParseFilters",
    "MessageMetric",
    "PriceMetric",
    "ParseTelegramCommand",
    "ParseNewsCommand",
    "TelegramParseFilters",
    "NewsParseFilters",
    "AnalyzeMessageCommand",
    "TriggeredBy",
]
