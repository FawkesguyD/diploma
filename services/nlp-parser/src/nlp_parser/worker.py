from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import aio_pika
import orjson
from aio_pika.abc import AbstractIncomingMessage

from aisi_contracts.envelope import Envelope
from aisi_contracts.messages import (
    AnalyzeMessageCommand,
    ParseNewsCommand,
    ParseTelegramCommand,
)
from aisi_contracts.metrics import MessageMetric

from nlp_parser.config import Settings
from nlp_parser.kafka_publisher import MessageMetricsPublisher
from nlp_parser.nlp import stub as nlp_stub
from nlp_parser.parsing.registry import get_adapter
from nlp_parser.persistence.mongo import (
    AnnotatedMessagesRepo,
    MessagesRepo,
    MongoClient,
)
from nlp_parser.persistence.postgres import ParserJobsRepo, PostgresClient, SourcesRepo
from nlp_parser.pubsub import MessagePubSub

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NlpParserWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        mongo: MongoClient,
        postgres: PostgresClient,
        publisher: MessageMetricsPublisher,
        pubsub: MessagePubSub,
    ) -> None:
        self._settings = settings
        self._mongo = mongo
        self._postgres = postgres
        self._publisher = publisher
        self._pubsub = pubsub
        self._messages = MessagesRepo(mongo.db)
        self._annotated = AnnotatedMessagesRepo(mongo.db)
        self._sources = SourcesRepo(postgres)
        self._jobs = ParserJobsRepo(postgres)
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._nlp_exchange: aio_pika.abc.AbstractExchange | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._processed_ids: set[str] = set()

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.worker_prefetch)

        tg_q = await self._channel.get_queue(self._settings.queue_parse_tg, ensure=False)
        news_q = await self._channel.get_queue(self._settings.queue_parse_news, ensure=False)
        analyze_q = await self._channel.get_queue(self._settings.queue_nlp_analyze, ensure=False)
        self._nlp_exchange = await self._channel.get_exchange(
            self._settings.exchange_nlp, ensure=False
        )

        self._tasks.append(asyncio.create_task(tg_q.consume(self._on_tg), name="nlp.parse.tg"))
        self._tasks.append(asyncio.create_task(news_q.consume(self._on_news), name="nlp.parse.news"))
        self._tasks.append(asyncio.create_task(analyze_q.consume(self._on_analyze), name="nlp.analyze"))
        logger.info(
            "NlpParserWorker подписался на %s, %s, %s",
            self._settings.queue_parse_tg,
            self._settings.queue_parse_news,
            self._settings.queue_nlp_analyze,
        )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self._channel is not None:
            await self._channel.close()
        if self._connection is not None:
            await self._connection.close()

    @staticmethod
    def _parse_envelope(body: bytes) -> dict[str, Any]:
        return orjson.loads(body)

    def _seen(self, message_id: str) -> bool:
        if not message_id:
            return False
        if message_id in self._processed_ids:
            return True
        self._processed_ids.add(message_id)
        if len(self._processed_ids) > 10_000:
            self._processed_ids = set(list(self._processed_ids)[-5_000:])
        return False

    async def _on_tg(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                env = self._parse_envelope(message.body)
                if self._seen(str(env.get("message_id"))):
                    return
                payload = ParseTelegramCommand.model_validate(env.get("payload") or {})
                correlation_id = env.get("correlation_id")
                await self._handle_parse(
                    source_id=payload.source_id,
                    since=payload.since,
                    limit=payload.limit,
                    correlation_id=correlation_id,
                    kind="tg",
                    job_id=payload.job_id,
                )
            except Exception:
                logger.exception("parse.tg: ошибка обработки сообщения")
                raise

    async def _on_news(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                env = self._parse_envelope(message.body)
                if self._seen(str(env.get("message_id"))):
                    return
                payload = ParseNewsCommand.model_validate(env.get("payload") or {})
                correlation_id = env.get("correlation_id")
                source = await self._sources.get(payload.source_id)
                kind = (source or {}).get("kind", "news")
                await self._handle_parse(
                    source_id=payload.source_id,
                    since=payload.since,
                    limit=None,
                    correlation_id=correlation_id,
                    kind=kind,
                    source_row=source,
                    job_id=payload.job_id,
                )
            except Exception:
                logger.exception("parse.news: ошибка обработки сообщения")
                raise

    async def _on_analyze(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                env = self._parse_envelope(message.body)
                if self._seen(str(env.get("message_id"))):
                    return
                payload = AnalyzeMessageCommand.model_validate(env.get("payload") or {})
                correlation_id = env.get("correlation_id")
                await self._handle_analyze(payload, correlation_id=correlation_id)
            except Exception:
                logger.exception("nlp.analyze: ошибка обработки сообщения")
                raise

    async def _handle_parse(
        self,
        *,
        source_id: UUID,
        since: datetime | None,
        limit: int | None,
        correlation_id: Any,
        kind: str,
        source_row: dict[str, Any] | None = None,
        job_id: UUID | None = None,
    ) -> None:
        if source_row is None:
            source_row = await self._sources.get(source_id)
        url_or_handle = (source_row or {}).get("url_or_handle", "")
        config = (source_row or {}).get("config") or {}
        adapter = get_adapter(kind)
        try:
            docs = await adapter(
                source_id,
                url_or_handle=url_or_handle,
                settings=self._settings,
                config=config,
                since=since,
                limit=limit,
            )
        except Exception as exc:
            if job_id is not None:
                await self._jobs.finish(job_id, status="failed", error=str(exc)[:500])
            raise
        await self._sources.mark_polled(source_id)
        for doc in docs:
            message_id = await self._messages.upsert_by_external_id(doc)
            await self._publish_analyze(message_id, correlation_id=correlation_id)
        if job_id is not None:
            await self._jobs.finish(
                job_id, status="succeeded", items_collected=len(docs)
            )
        logger.info(
            "parse.%s: source=%s — upsert %d сообщений", kind, source_id, len(docs)
        )

    async def _publish_analyze(self, message_id: str, *, correlation_id: Any) -> None:
        if self._nlp_exchange is None:
            logger.warning("nlp.exchange недоступен — analyze не публикуем")
            return
        envelope = Envelope[AnalyzeMessageCommand](
            payload=AnalyzeMessageCommand(message_id=message_id),
            correlation_id=correlation_id or uuid4(),
        )
        msg = aio_pika.Message(
            body=orjson.dumps(envelope.model_dump(mode="json")),
            content_type="application/json",
            message_id=str(envelope.message_id),
            correlation_id=str(envelope.correlation_id),
        )
        await self._nlp_exchange.publish(msg, routing_key=self._settings.routing_key_nlp_analyze)

    async def _handle_analyze(
        self, cmd: AnalyzeMessageCommand, *, correlation_id: Any
    ) -> None:
        doc = await self._messages.get(cmd.message_id)
        if doc is None:
            logger.warning("nlp.analyze: message %s не найдено", cmd.message_id)
            return
        if not cmd.force:
            existing = await self._annotated.get_active(cmd.message_id)
            if existing is not None:
                logger.info("nlp.analyze: %s уже аннотировано — пропускаем", cmd.message_id)
                return
        text_value: str = doc.get("text") or ""
        result = nlp_stub.analyze(text_value, lang_hint=cmd.lang_hint or doc.get("lang"))
        await self._annotated.upsert_version(
            message_id=cmd.message_id,
            model_run_id=self._settings.nlp_model_run_id,
            models=nlp_stub.model_versions(),
            is_ad=result.is_ad,
            ad_score=result.ad_score,
            topics=result.topics,
            sentiment_label=result.sentiment_label,
            sentiment_score=result.sentiment_score,
            entities=result.entities,
            lang=result.lang,
            summary=result.summary,
        )
        await self._emit_metric(doc=doc, result=result, correlation_id=correlation_id)
        await self._pubsub.publish(
            {
                "id": cmd.message_id,
                "source_id": str(doc.get("source_id")),
                "channel_kind": doc.get("channel_kind"),
                "channel_site": doc.get("channel_site"),
                "url": doc.get("url"),
                "published_at": (doc.get("published_at") or _utcnow()).isoformat()
                if isinstance(doc.get("published_at"), datetime)
                else doc.get("published_at"),
                "text": text_value,
                "lang": result.lang,
                "annotation": {
                    "is_ad": result.is_ad,
                    "ad_score": result.ad_score,
                    "topics": result.topics,
                    "sentiment": {"label": result.sentiment_label, "score": result.sentiment_score},
                    "entities": result.entities,
                },
            }
        )

    async def _emit_metric(
        self,
        *,
        doc: dict[str, Any],
        result: nlp_stub.NlpResult,
        correlation_id: Any,
    ) -> None:
        if not self._publisher.is_started:
            return
        topic_slug = result.topics[0]["slug"] if result.topics else "uncategorized"
        topic_score = float(result.topics[0]["score"]) if result.topics else 0.0
        districts = [
            e["district_slug"]
            for e in result.entities
            if e.get("type") == "location" and e.get("district_slug")
        ]
        developers = [e["text"] for e in result.entities if e.get("type") == "developer"]
        source_id_raw = doc.get("source_id")
        try:
            source_uuid = UUID(str(source_id_raw))
        except (TypeError, ValueError):
            logger.warning("metric: некорректный source_id %r — пропускаем", source_id_raw)
            return
        metric = MessageMetric(
            event_time=_utcnow(),
            published_at=doc.get("published_at") or _utcnow(),
            message_id=str(doc.get("_id")),
            source_id=source_uuid,
            channel_kind=doc.get("channel_kind") or "tg",
            channel_site=doc.get("channel_site") or "unknown",
            topic_slug=topic_slug,
            topic_score=topic_score,
            topics_all=[t["slug"] for t in result.topics],
            sentiment_label=result.sentiment_label,
            sentiment_score=result.sentiment_score,
            is_ad=result.is_ad,
            lang=result.lang,
            entities_districts=districts,
            entities_developers=developers,
            model_run_id=UUID(self._settings.nlp_model_run_id),
        )
        await self._publisher.publish_message(metric, correlation_id=correlation_id)


__all__ = ["NlpParserWorker"]
