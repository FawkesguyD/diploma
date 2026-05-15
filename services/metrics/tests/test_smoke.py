"""Smoke-тесты сервиса metrics.

Не требуют внешних сервисов: ClickHouse-клиент мокается, Kafka-consumer
не стартует (`enable_consumers_on_startup=False`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aisi_contracts.envelope import Envelope
from aisi_contracts.metrics import MessageMetric, PriceMetric

from metrics import main as main_mod
from metrics.cache import TTLCache, make_key, ttl_for_granularity
from metrics.config import get_settings


class _FakeCH:
    """Минимальный стаб ClickHouseClient: каждый query возвращает []."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start(self) -> None:  # noqa: D401
        return None

    async def stop(self) -> None:  # noqa: D401
        return None

    async def ping(self) -> bool:
        return True

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append((sql, params or {}))
        return []

    async def insert_rows(self, *_a: Any, **_kw: Any) -> None:
        return None


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch):
    # Отключаем consumer-ы — иначе попытается достучаться до Kafka.
    monkeypatch.setenv("ENABLE_CONSUMERS_ON_STARTUP", "false")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(main_mod, "ClickHouseClient", _FakeCH)
    return main_mod.app


def test_healthz(app):
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["clickhouse"] is True


def test_dashboard_endpoints_empty_payload(app):
    """На пустом ClickHouse каждый эндпоинт возвращает 200 + points: []."""
    paths = [
        "/api/dashboards/overview",
        "/api/dashboards/prices/timeseries",
        "/api/dashboards/prices/distribution",
        "/api/dashboards/prices/by-district",
        "/api/dashboards/topics/activity?topic=badaevsky_complex",
        "/api/dashboards/topics/cooccurrence",
        "/api/dashboards/sentiment/by-district",
        "/api/dashboards/model-quality",
        "/api/dashboards/model-quality/undervalued-share",
        "/api/dashboards/listings/by-channel",
        "/api/dashboards/objects/top-undervalued",
    ]
    with TestClient(app) as client:
        for path in paths:
            r = client.get(path)
            assert r.status_code == 200, (path, r.text)
            body = r.json()
            assert isinstance(body, dict)
            # /overview не отдаёт points; остальные — points: list
            if "points" in body:
                assert body["points"] == []


def test_message_metric_envelope_roundtrip():
    """Envelope[MessageMetric] сериализуется/десериализуется."""
    m = MessageMetric(
        event_time=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        message_id="65f8a1b2c3d4e5f6a7b8c9d0",
        source_id=uuid4(),
        channel_kind="tg",
        channel_site="t.me",
        topic_slug="badaevsky_complex",
        topic_score=0.91,
        topics_all=["badaevsky_complex", "mortgage_rates"],
        sentiment_label="neutral",
        sentiment_score=0.62,
        is_ad=False,
        lang="ru",
        entities_districts=["presnenskiy"],
        entities_developers=["Capital Group"],
        model_run_id=uuid4(),
    )
    env = Envelope[MessageMetric](payload=m)
    blob = env.model_dump_json()
    parsed = Envelope[MessageMetric].model_validate_json(blob)
    assert parsed.payload.topic_slug == "badaevsky_complex"


def test_price_metric_envelope_roundtrip():
    p = PriceMetric(
        event_time=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        object_id="65f8a1b2c3d4e5f6a7b8c9d1",
        source_id=uuid4(),
        object_kind="residential",
        channel_site="cian.ru",
        city="Moscow",
        district_slug="presnenskiy",
        rooms=2,
        area=52.4,
        floor=7,
        year_built=2008,
        price_real=14_500_000,
        price_predicted=16_200_000,
        deviation_abs=-1_700_000,
        deviation_pct=-10.49,
        is_undervalued=True,
        rank_in_run=3,
        model_version="v1.0",
        model_run_id=uuid4(),
    )
    env = Envelope[PriceMetric](payload=p)
    parsed = Envelope[PriceMetric].model_validate_json(env.model_dump_json())
    assert parsed.payload.is_undervalued is True


def test_cache_ttl_and_lru():
    cache = TTLCache(max_entries=2)
    cache.set("a", 1, ttl_s=60)
    cache.set("b", 2, ttl_s=60)
    assert cache.get("a") == 1
    cache.set("c", 3, ttl_s=60)  # выкидывает 'b' (LRU)
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert ttl_for_granularity("hour") > 0
    assert make_key("p", {"x": 1, "y": [1, 2]}) == "p|x=1|y=1,2"
