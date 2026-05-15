from __future__ import annotations

import logging
from typing import Any

import orjson
from aiokafka import AIOKafkaProducer

from aisi_contracts.envelope import Envelope
from aisi_contracts.metrics import MessageMetric

from nlp_parser.config import Settings

logger = logging.getLogger(__name__)


def _serialize(value: Any) -> bytes:
    return orjson.dumps(value, default=str)


class MessageMetricsPublisher:
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

    @property
    def is_started(self) -> bool:
        return self._producer is not None

    async def publish_message(
        self, metric: MessageMetric, *, correlation_id: Any = None
    ) -> None:
        if self._producer is None:
            raise RuntimeError("Publisher не стартанут (start()).")
        envelope = Envelope[MessageMetric](
            payload=metric,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )
        await self._producer.send_and_wait(
            self._settings.kafka_topic_messages,
            value=envelope.model_dump(mode="json"),
            key=str(metric.source_id),
        )


__all__ = ["MessageMetricsPublisher"]
