"""Producer для топика `metrics.prices`.

Сообщение — Envelope[PriceMetric] (JSON, UTF-8). Ключ партиционирования —
`object_id` (см. messaging/README.md).
"""
from __future__ import annotations

import logging
from typing import Any

import orjson
from aiokafka import AIOKafkaProducer

from aisi_contracts.envelope import Envelope
from aisi_contracts.metrics import PriceMetric

from realestate.config import Settings

logger = logging.getLogger(__name__)


def _serialize(value: Any) -> bytes:
    return orjson.dumps(value, default=str)


class PriceMetricsPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap,
            value_serializer=_serialize,
            key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
            enable_idempotence=True,
            acks="all",
        )
        await self._producer.start()
        logger.info("Kafka producer started: %s", self._settings.kafka_bootstrap)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish_price(self, metric: PriceMetric, *, correlation_id=None) -> None:
        assert self._producer is not None, "Publisher не стартанут (start())."
        envelope = Envelope[PriceMetric](
            payload=metric,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )
        await self._producer.send_and_wait(
            self._settings.kafka_topic_prices,
            value=envelope.model_dump(mode="json"),
            key=metric.object_id,
        )


__all__ = ["PriceMetricsPublisher"]
