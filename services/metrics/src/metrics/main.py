"""FastAPI-приложение `metrics`.

Lifecycle:
* startup — поднимаем ClickHouse-клиент и (опционально) два Kafka-consumer'а
  (`metrics.messages` → `events_messages`, `metrics.prices` → `events_prices`);
* shutdown — гасим consumer'ов (с финальным flush) и закрываем CH-соединение.

Если ClickHouse / Kafka недоступны — поднимаемся всё равно, но
эндпоинты вернут 503 / consumer'ы будут retry'ить INSERT (см. consumer.py).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from metrics.api.listings import router as listings_router
from metrics.api.model_quality import router as model_quality_router
from metrics.api.objects import router as objects_router
from metrics.api.overview import router as overview_router
from metrics.api.prices import router as prices_router
from metrics.api.sentiment import router as sentiment_router
from metrics.api.topics import router as topics_router
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient
from metrics.config import get_settings
from metrics.consumer import (
    BaseBatchingConsumer,
    make_messages_consumer,
    make_prices_consumer,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.cache = TTLCache(max_entries=settings.cache_max_entries)

    ch = ClickHouseClient(settings)
    app.state.ch = ch
    app.state.consumers = []

    try:
        await ch.start()
    except Exception:  # noqa: BLE001
        logger.exception("ClickHouse не стартанул — /api/dashboards/* будут возвращать 503.")

    if settings.enable_consumers_on_startup:
        consumers: list[BaseBatchingConsumer] = []
        for factory in (make_messages_consumer, make_prices_consumer):
            try:
                c = factory(settings, ch)
                await c.start()
                consumers.append(c)
            except Exception:  # noqa: BLE001
                logger.exception("Не удалось поднять consumer (%s); пропускаем.", factory.__name__)
        app.state.consumers = consumers

    try:
        yield
    finally:
        for c in app.state.consumers:
            try:
                await c.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Consumer.stop() failed")
        await ch.stop()


app = FastAPI(title="AIS metrics", version="0.1.0", lifespan=lifespan)
app.include_router(overview_router)
app.include_router(prices_router)
app.include_router(topics_router)
app.include_router(sentiment_router)
app.include_router(model_quality_router)
app.include_router(listings_router)
app.include_router(objects_router)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, object]:
    ch: ClickHouseClient = app.state.ch
    ch_ok = await ch.ping() if ch else False
    return {
        "status": "ok",
        "clickhouse": ch_ok,
        "consumers": len(getattr(app.state, "consumers", []) or []),
    }
