"""Smoke-тесты: контракты импортируются, FastAPI-app собирается."""
from __future__ import annotations

from uuid import UUID

from aisi_contracts.envelope import Envelope, SCHEMA_VERSION
from aisi_contracts.metrics import PriceMetric
from aisi_contracts.realestate import RankCommand, ScoreCommand


def test_envelope_defaults_and_schema_version():
    payload = ScoreCommand(object_ids=["65f8a1b2c3d4e5f6a7b8c9d0"])
    env = Envelope[ScoreCommand](payload=payload)
    assert env.schema_version == SCHEMA_VERSION == "v1"
    assert isinstance(env.message_id, UUID)
    assert isinstance(env.correlation_id, UUID)
    assert env.payload.object_ids == ["65f8a1b2c3d4e5f6a7b8c9d0"]


def test_score_command_requires_object_ids():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ScoreCommand(object_ids=[])


def test_rank_command_default_scope():
    cmd = RankCommand.model_validate({"model_run_id": "00000000-0000-0000-0000-000000000001"})
    assert cmd.scope.city is None
    assert cmd.scope.district_slug is None


def test_price_metric_serialises():
    from datetime import datetime, timezone

    metric = PriceMetric(
        event_time=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        object_id="65f8a1b2c3d4e5f6a7b8c9d0",
        source_id=UUID("00000000-0000-0000-0000-000000000002"),
        object_kind="residential",
        channel_site="cian.ru",
        price_predicted=16_200_000.0,
        is_undervalued=True,
        model_version="v1.0",
        model_run_id=UUID("00000000-0000-0000-0000-000000000003"),
    )
    blob = Envelope[PriceMetric](payload=metric).model_dump_json()
    assert "metrics" not in blob  # топик/канал не утекает в payload
    assert "price_predicted" in blob


def test_app_imports():
    """Главный модуль импортируется (без подключения к инфре)."""
    from realestate import main  # noqa: F401

    assert main.app.title == "AIS realestate"
