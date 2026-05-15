from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from aisi_contracts.envelope import Envelope
from aisi_contracts.realestate import ParseRealestateCommand, RealestateParseFilters


def test_parse_command_minimal_payload():
    cmd = ParseRealestateCommand.model_validate(
        {"source_id": "00000000-0000-0000-0000-000000000010"}
    )
    assert cmd.source_id == UUID("00000000-0000-0000-0000-000000000010")
    assert cmd.filters is None
    assert cmd.triggered_by == "schedule"


def test_parse_command_with_filters():
    cmd = ParseRealestateCommand(
        source_id=UUID("00000000-0000-0000-0000-000000000011"),
        filters=RealestateParseFilters(city="Moscow", rooms=[1, 2], price_max=30_000_000),
        triggered_by="manual",
    )
    assert cmd.filters is not None
    assert cmd.filters.city == "Moscow"
    assert cmd.filters.rooms == [1, 2]
    assert cmd.filters.price_max == 30_000_000


def test_parse_command_rejects_negative_price_max():
    with pytest.raises(ValidationError):
        RealestateParseFilters(price_max=-1)


def test_parse_command_rejects_unknown_trigger():
    with pytest.raises(ValidationError):
        ParseRealestateCommand.model_validate(
            {"source_id": "00000000-0000-0000-0000-000000000012", "triggered_by": "cron"}
        )


def test_envelope_roundtrip_json():
    payload = ParseRealestateCommand(
        source_id=UUID("00000000-0000-0000-0000-000000000013"),
        filters=RealestateParseFilters(city="Moscow"),
        triggered_by="backfill",
    )
    env = Envelope[ParseRealestateCommand](payload=payload)
    blob = env.model_dump_json()
    parsed = Envelope[ParseRealestateCommand].model_validate_json(blob)
    assert parsed.payload.source_id == payload.source_id
    assert parsed.payload.filters is not None
    assert parsed.payload.filters.city == "Moscow"
    assert parsed.payload.triggered_by == "backfill"
    assert parsed.message_id == env.message_id
