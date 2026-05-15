"""RabbitMQ consumer для очередей `realestate.score` и `realestate.rank`.

Топология описана в `docs/design/messaging/README.md`. Здесь мы только
подписываемся на уже существующие queues (их создаёт `infra/rabbitmq`
через `definitions.json`).
"""
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
from aisi_contracts.metrics import PriceMetric
from aisi_contracts.realestate import ParseRealestateCommand, RankCommand, ScoreCommand
from aisi_redis import RedisSettings, get_client, is_duplicate
from aisi_redis.dedup import DEDUP_TTL_INGEST, DEDUP_TTL_PROCESS

from realestate.config import Settings
from realestate.kafka.publisher import PriceMetricsPublisher
from realestate.ml.predict import ModelHolder, predict
from realestate.parsing import parse_source
from realestate.persistence.mongo import AnnotatedObjectsRepo, MongoClient, ObjectsRepo
from realestate.persistence.postgres import ModelRunsRepo, PostgresClient

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RealestateWorker:
    """Один объект — два consumer-loop'а (score + rank)."""

    def __init__(
        self,
        *,
        settings: Settings,
        mongo: MongoClient,
        postgres: PostgresClient,
        model_holder: ModelHolder,
        publisher: PriceMetricsPublisher,
        active_model_id: UUID,
        active_model_version: str,
    ) -> None:
        self._settings = settings
        self._mongo = mongo
        self._postgres = postgres
        self._model = model_holder
        self._publisher = publisher
        self._active_model_id = active_model_id
        self._active_model_version = active_model_version
        self._objects = ObjectsRepo(mongo.db)
        self._annotated = AnnotatedObjectsRepo(mongo.db)
        self._runs = ModelRunsRepo(postgres)
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._realestate_exchange: aio_pika.abc.AbstractExchange | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._processed_message_ids: set[str] = set()  # упрощённый idempotency-cache
        self._redis = get_client(
            RedisSettings(
                REDIS_HOST=settings.redis_host,
                REDIS_PORT=settings.redis_port,
                REDIS_PASSWORD=settings.redis_password,
            )
        )

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._settings.worker_prefetch)

        score_q = await self._channel.get_queue(self._settings.queue_score, ensure=False)
        rank_q = await self._channel.get_queue(self._settings.queue_rank, ensure=False)
        parse_q = await self._channel.get_queue(self._settings.queue_parse, ensure=False)
        self._realestate_exchange = await self._channel.get_exchange(
            self._settings.exchange_realestate, ensure=False
        )

        self._tasks.append(asyncio.create_task(score_q.consume(self._on_score), name="re.score"))
        self._tasks.append(asyncio.create_task(rank_q.consume(self._on_rank), name="re.rank"))
        self._tasks.append(asyncio.create_task(parse_q.consume(self._on_parse), name="re.parse"))
        logger.info(
            "RealestateWorker подписался на %s, %s, %s",
            self._settings.queue_score,
            self._settings.queue_rank,
            self._settings.queue_parse,
        )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_envelope(body: bytes) -> dict[str, Any]:
        return orjson.loads(body)

    def _seen(self, message_id: str) -> bool:
        if message_id in self._processed_message_ids:
            return True
        self._processed_message_ids.add(message_id)
        # TODO: вынести в Redis/Mongo с TTL для нескольких реплик.
        if len(self._processed_message_ids) > 10_000:
            self._processed_message_ids = set(list(self._processed_message_ids)[-5_000:])
        return False

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _on_score(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                envelope_raw = self._parse_envelope(message.body)
                message_id = str(envelope_raw.get("message_id"))
                correlation_id = envelope_raw.get("correlation_id")
                if message_id and self._seen(message_id):
                    logger.info("score: дубликат %s — пропускаем", message_id)
                    return
                payload = ScoreCommand.model_validate(envelope_raw.get("payload") or {})
                await self._handle_score(payload, correlation_id=correlation_id)
            except Exception:  # pragma: no cover - integration path
                logger.exception("score: ошибка обработки сообщения")
                raise

    async def _on_rank(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                envelope_raw = self._parse_envelope(message.body)
                message_id = str(envelope_raw.get("message_id"))
                if message_id and self._seen(message_id):
                    return
                payload = RankCommand.model_validate(envelope_raw.get("payload") or {})
                await self._handle_rank(payload)
            except Exception:
                logger.exception("rank: ошибка обработки сообщения")
                raise

    async def _on_parse(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                envelope_raw = self._parse_envelope(message.body)
                message_id = str(envelope_raw.get("message_id"))
                correlation_id = envelope_raw.get("correlation_id")
                if message_id and self._seen(message_id):
                    logger.info("parse: дубликат %s — пропускаем", message_id)
                    return
                payload = ParseRealestateCommand.model_validate(envelope_raw.get("payload") or {})
                await self._handle_parse(payload, correlation_id=correlation_id)
            except Exception:
                logger.exception("parse: ошибка обработки сообщения")
                raise

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------

    async def _handle_score(self, cmd: ScoreCommand, *, correlation_id: Any = None) -> None:
        run_id = await self._runs.create(
            module=self._settings.module_name,
            model_id=self._active_model_id,
            triggered_by="queue",
        )
        processed_ids: list[str] = []
        errors: list[str] = []
        try:
            docs = await self._objects.get_many(cmd.object_ids)
            doc_by_id = {str(d["_id"]): d for d in docs}
            for object_id in cmd.object_ids:
                doc = doc_by_id.get(object_id)
                if doc is None:
                    errors.append(f"object {object_id} not found")
                    continue
                if await is_duplicate(
                    self._redis, "eval", object_id=object_id, ttl=DEDUP_TTL_PROCESS
                ):
                    logger.info("score: redis-dedup пропускает %s", object_id)
                    continue
                try:
                    result = predict(self._model, doc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("score: predict failed for %s", object_id)
                    errors.append(f"{object_id}: {exc}")
                    continue

                await self._annotated.upsert_version(
                    object_id=object_id,
                    model_run_id=str(run_id),
                    model_version=self._active_model_version,
                    predicted_price=result.predicted_price,
                    deviation_abs=result.delta_abs,
                    deviation_pct=result.delta_pct,
                    is_undervalued=result.is_undervalued,
                    features_used=result.features_used,
                )
                await self._runs.increment_processed(run_id)
                processed_ids.append(object_id)

                listing = doc.get("listing") or {}
                address = listing.get("address") or {}
                metric = PriceMetric(
                    event_time=_utcnow(),
                    published_at=doc.get("published_at") or _utcnow(),
                    object_id=object_id,
                    source_id=UUID(str(doc.get("source_id"))) if doc.get("source_id") else uuid4(),
                    object_kind=doc.get("object_kind") or "residential",
                    channel_site=doc.get("channel_site") or "unknown",
                    city=address.get("city"),
                    district_slug=address.get("district_slug"),
                    rooms=listing.get("rooms"),
                    area=listing.get("area"),
                    floor=listing.get("floor"),
                    year_built=listing.get("year_built"),
                    price_real=result.listing_price,
                    price_predicted=result.predicted_price,
                    deviation_abs=result.delta_abs,
                    deviation_pct=result.delta_pct,
                    is_undervalued=result.is_undervalued,
                    rank_in_run=None,
                    model_version=self._active_model_version,
                    model_run_id=run_id,
                )
                await self._publisher.publish_price(metric, correlation_id=correlation_id)

            await self._runs.finish(
                run_id,
                status="succeeded" if not errors else "failed" if not processed_ids else "succeeded",
                error="; ".join(errors) if errors else None,
                result_ref={"collection": "annotated_objects", "object_ids": processed_ids},
            )

            # Auto-rank, если батч большой.
            if len(processed_ids) >= self._settings.rank_threshold:
                await self._handle_rank(
                    RankCommand(model_run_id=run_id),  # type: ignore[arg-type]
                )
        except Exception as exc:  # noqa: BLE001
            await self._runs.finish(run_id, status="failed", error=str(exc))
            raise

    async def _handle_rank(self, cmd: RankCommand) -> None:
        run_id = str(cmd.model_run_id)
        scope = cmd.scope
        items: list[dict[str, Any]] = []
        async for doc in self._annotated.iter_by_run(run_id):
            items.append(doc)

        if scope.city or scope.district_slug:
            # подгружаем соответствующие объекты для фильтрации
            ids = [str(d["object_id"]) for d in items]
            objects = await self._objects.get_many(ids)
            obj_by_id = {str(o["_id"]): o for o in objects}
            filtered: list[dict[str, Any]] = []
            for item in items:
                obj = obj_by_id.get(str(item["object_id"]))
                if obj is None:
                    continue
                address = (obj.get("listing") or {}).get("address") or {}
                if scope.city and address.get("city") != scope.city:
                    continue
                if scope.district_slug and address.get("district_slug") != scope.district_slug:
                    continue
                filtered.append(item)
            items = filtered

        # Ранжируем по deviation_pct (меньше = недооценённее).
        items.sort(key=lambda d: (d.get("deviation_pct") is None, d.get("deviation_pct") or 0.0))
        for rank, item in enumerate(items, start=1):
            await self._annotated.update_rank(str(item["object_id"]), run_id, rank)
        logger.info("rank: переранжировано %d объектов для run %s", len(items), run_id)

    async def _handle_parse(
        self, cmd: ParseRealestateCommand, *, correlation_id: Any = None
    ) -> None:
        filters = cmd.filters.model_dump(exclude_none=True) if cmd.filters else None
        listings = await parse_source(cmd.source_id, filters)
        object_ids: list[str] = []
        skipped = 0
        for listing in listings:
            site = str(listing.get("channel_site") or "unknown")
            ext_id = str(listing.get("external_id") or "")
            if ext_id and await is_duplicate(
                self._redis, "obj", site=site, external_id=ext_id, ttl=DEDUP_TTL_INGEST
            ):
                skipped += 1
                continue
            inserted_id = await self._objects.upsert_by_external_id(listing)
            object_ids.append(inserted_id)
        logger.info(
            "parse: source=%s triggered_by=%s — upsert %d объектов (dedup отсёк %d)",
            cmd.source_id,
            cmd.triggered_by,
            len(object_ids),
            skipped,
        )
        if not object_ids:
            return
        if self._realestate_exchange is None:
            logger.warning("parse: realestate.exchange недоступен — score не публикуем")
            return
        envelope = Envelope[ScoreCommand](
            payload=ScoreCommand(object_ids=object_ids),
            correlation_id=correlation_id or uuid4(),
        )
        msg = aio_pika.Message(
            body=orjson.dumps(envelope.model_dump(mode="json")),
            content_type="application/json",
            message_id=str(envelope.message_id),
            correlation_id=str(envelope.correlation_id),
        )
        await self._realestate_exchange.publish(
            msg, routing_key=self._settings.routing_key_score
        )


__all__ = ["RealestateWorker"]
