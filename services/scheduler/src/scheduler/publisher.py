from __future__ import annotations

import logging
from uuid import UUID, uuid4

import aio_pika
import orjson
from aio_pika.abc import AbstractRobustConnection
from aisi_contracts.envelope import Envelope
from aisi_contracts.messages import ParseNewsCommand, ParseTelegramCommand
from aisi_contracts.realestate import ParseRealestateCommand

from .config import Settings

logger = logging.getLogger(__name__)


class ParserPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: AbstractRobustConnection | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        logger.info("scheduler.publisher.connected", extra={"url": self._settings.rabbitmq_url})

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def publish_parse(self, *, kind: str, source_id: UUID, job_id: UUID | None) -> None:
        if self._connection is None:
            raise RuntimeError("publisher is not connected")

        if kind == "tg":
            envelope = Envelope[ParseTelegramCommand](
                payload=ParseTelegramCommand(
                    source_id=source_id, triggered_by="schedule", job_id=job_id
                ),
                correlation_id=uuid4(),
            )
            routing_key = self._settings.routing_key_parse_tg
            exchange_name = self._settings.exchange_parser
            body = orjson.dumps(envelope.model_dump(mode="json"))
            message_id = str(envelope.message_id)
            correlation_id = str(envelope.correlation_id)
        elif kind in {"news", "rss", "html"}:
            news_envelope = Envelope[ParseNewsCommand](
                payload=ParseNewsCommand(
                    source_id=source_id, triggered_by="schedule", job_id=job_id
                ),
                correlation_id=uuid4(),
            )
            routing_key = self._settings.routing_key_parse_news
            exchange_name = self._settings.exchange_parser
            body = orjson.dumps(news_envelope.model_dump(mode="json"))
            message_id = str(news_envelope.message_id)
            correlation_id = str(news_envelope.correlation_id)
        elif kind == "realestate":
            re_envelope = Envelope[ParseRealestateCommand](
                payload=ParseRealestateCommand(
                    source_id=source_id, triggered_by="schedule"
                ),
                correlation_id=uuid4(),
            )
            routing_key = self._settings.routing_key_parse_realestate
            exchange_name = self._settings.exchange_parser
            body = orjson.dumps(re_envelope.model_dump(mode="json"))
            message_id = str(re_envelope.message_id)
            correlation_id = str(re_envelope.correlation_id)
        else:
            raise ValueError(f"unsupported kind for scheduler: {kind}")

        channel = await self._connection.channel()
        try:
            exchange = await channel.get_exchange(exchange_name, ensure=False)
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    message_id=message_id,
                    correlation_id=correlation_id,
                ),
                routing_key=routing_key,
            )
        finally:
            await channel.close()
