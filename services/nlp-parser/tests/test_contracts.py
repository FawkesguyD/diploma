from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from aisi_contracts.envelope import SCHEMA_VERSION, Envelope
from aisi_contracts.messages import (
    AnalyzeMessageCommand,
    ParseNewsCommand,
    ParseTelegramCommand,
    TelegramParseFilters,
)


def test_parse_tg_command_minimal():
    cmd = ParseTelegramCommand.model_validate(
        {"source_id": "00000000-0000-0000-0000-000000000010"}
    )
    assert cmd.source_id == UUID("00000000-0000-0000-0000-000000000010")
    assert cmd.triggered_by == "schedule"
    assert cmd.since is None
    assert cmd.limit is None


def test_parse_tg_command_limit_bounds():
    with pytest.raises(ValidationError):
        ParseTelegramCommand(
            source_id=UUID("00000000-0000-0000-0000-000000000010"), limit=0
        )
    with pytest.raises(ValidationError):
        ParseTelegramCommand(
            source_id=UUID("00000000-0000-0000-0000-000000000010"), limit=10_000
        )


def test_parse_tg_command_rejects_unknown_trigger():
    with pytest.raises(ValidationError):
        ParseTelegramCommand.model_validate(
            {
                "source_id": "00000000-0000-0000-0000-000000000010",
                "triggered_by": "cron",
            }
        )


def test_parse_news_command_with_since():
    cmd = ParseNewsCommand.model_validate(
        {
            "source_id": "00000000-0000-0000-0000-000000000011",
            "since": "2026-05-01T00:00:00Z",
            "triggered_by": "backfill",
        }
    )
    assert cmd.triggered_by == "backfill"
    assert cmd.since is not None


def test_analyze_message_command_requires_message_id():
    with pytest.raises(ValidationError):
        AnalyzeMessageCommand.model_validate({})


def test_analyze_message_command_defaults():
    cmd = AnalyzeMessageCommand(message_id="65f8a1b2c3d4e5f6a7b8c9d0")
    assert cmd.force is False
    assert cmd.lang_hint is None


def test_envelope_roundtrip():
    payload = ParseTelegramCommand(
        source_id=UUID("00000000-0000-0000-0000-000000000012"),
        triggered_by="manual",
    )
    env = Envelope[ParseTelegramCommand](payload=payload)
    assert env.schema_version == SCHEMA_VERSION == "v1"
    blob = env.model_dump_json()
    parsed = Envelope[ParseTelegramCommand].model_validate_json(blob)
    assert parsed.payload.source_id == payload.source_id
    assert parsed.message_id == env.message_id


def test_telegram_parse_filters_extra_ignored():
    f = TelegramParseFilters.model_validate({"limit": 100, "unknown": "x"})
    assert f.limit == 100
