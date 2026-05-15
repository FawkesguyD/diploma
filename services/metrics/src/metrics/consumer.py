"""Kafka → ClickHouse: два consumer'а (`metrics.messages`, `metrics.prices`).

Логика общая (см. `BaseBatchingConsumer`):

* `auto_offset_reset='earliest'`, `enable_auto_commit=False` — оффсеты
  коммитятся вручную после успешного `INSERT` в ClickHouse, чтобы при
  падении сервиса ничего не потерять. Дубли исключает MV-семейство
  (`ReplacingMergeTree` для `events_prices`) + идемпотентность по
  `(object_id, model_version)` / `(message_id, event_time)` на стороне
  приложения.
* Батч пишется при достижении `BATCH_SIZE` или по таймауту `BATCH_TIMEOUT_S`.
* Ошибки CH → лог + повтор того же батча; сообщения остаются
  не-закоммиченными, поэтому Kafka передаст их снова после рестарта.

Маппинг JSON → колонки таблицы — статический (`_MESSAGE_COLUMNS` /
`_PRICE_COLUMNS`), Pydantic-модели контрактов используем для валидации.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Sequence

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition

from aisi_contracts.envelope import Envelope
from aisi_contracts.metrics import MessageMetric, PriceMetric

from metrics.clickhouse import ClickHouseClient
from metrics.config import Settings

logger = logging.getLogger(__name__)


# --- маппинг колонок (порядок важен — это порядок аргументов в insert) ---

_MESSAGE_COLUMNS: tuple[str, ...] = (
    "event_time",
    "published_at",
    "message_id",
    "source_id",
    "channel_kind",
    "channel_site",
    "topic_slug",
    "topic_score",
    "topics_all",
    "sentiment_label",
    "sentiment_score",
    "is_ad",
    "lang",
    "entities_districts",
    "entities_developers",
    "model_run_id",
)

_PRICE_COLUMNS: tuple[str, ...] = (
    "event_time",
    "published_at",
    "object_id",
    "source_id",
    "object_kind",
    "channel_site",
    "city",
    "district_slug",
    "rooms",
    "area",
    "floor",
    "year_built",
    "price_real",
    "price_predicted",
    "deviation_abs",
    "deviation_pct",
    "is_undervalued",
    "rank_in_run",
    "model_version",
    "model_run_id",
)


def _message_row(m: MessageMetric) -> list[Any]:
    return [
        m.event_time,
        m.published_at,
        m.message_id,
        m.source_id,
        m.channel_kind,
        m.channel_site,
        m.topic_slug,
        float(m.topic_score),
        list(m.topics_all),
        m.sentiment_label,
        float(m.sentiment_score),
        1 if m.is_ad else 0,
        m.lang,
        list(m.entities_districts),
        list(m.entities_developers),
        m.model_run_id,
    ]


def _price_row(p: PriceMetric) -> list[Any]:
    return [
        p.event_time,
        p.published_at,
        p.object_id,
        p.source_id,
        p.object_kind,
        p.channel_site,
        p.city or "",
        p.district_slug or "",
        int(p.rooms or 0),
        float(p.area or 0.0),
        int(p.floor or 0),
        int(p.year_built or 0),
        float(p.price_real) if p.price_real is not None else 0.0,
        float(p.price_predicted),
        float(p.deviation_abs) if p.deviation_abs is not None else 0.0,
        float(p.deviation_pct) if p.deviation_pct is not None else 0.0,
        1 if p.is_undervalued else 0,
        int(p.rank_in_run or 0),
        p.model_version,
        p.model_run_id,
    ]


@dataclass
class _Buffered:
    row: list[Any]
    tp: TopicPartition
    offset: int


class BaseBatchingConsumer:
    """Один топик → одна таблица. Батчинг по размеру/времени, ручной commit."""

    def __init__(
        self,
        *,
        settings: Settings,
        ch: ClickHouseClient,
        topic: str,
        group_id: str,
        table: str,
        columns: Sequence[str],
        payload_parser: Callable[[dict[str, Any]], list[Any]],
    ) -> None:
        self._settings = settings
        self._ch = ch
        self._topic = topic
        self._group_id = group_id
        self._table = table
        self._columns = tuple(columns)
        self._parse = payload_parser

        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._settings.kafka_bootstrap,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._run(), name=f"metrics-consumer-{self._topic}")
        logger.info("Consumer started: topic=%s group=%s", self._topic, self._group_id)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
        if self._consumer is not None:
            await self._consumer.stop()
        logger.info("Consumer stopped: topic=%s", self._topic)

    async def _flush(self, buf: list[_Buffered]) -> None:
        if not buf:
            return
        rows = [b.row for b in buf]
        # Retry-цикл: пока ClickHouse не примет — не коммитим оффсеты.
        delay = 1.0
        while True:
            try:
                await self._ch.insert_rows(self._table, self._columns, rows)
                break
            except Exception:  # noqa: BLE001
                logger.exception(
                    "INSERT INTO %s (%d rows) failed; retrying in %.1fs",
                    self._table, len(rows), delay,
                )
                if self._stop_event.is_set():
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)

        # Берём максимальный offset на партицию и коммитим (Kafka хочет next-to-read).
        offsets: dict[TopicPartition, int] = {}
        for b in buf:
            cur = offsets.get(b.tp)
            if cur is None or b.offset > cur:
                offsets[b.tp] = b.offset
        assert self._consumer is not None
        await self._consumer.commit({tp: off + 1 for tp, off in offsets.items()})
        logger.debug(
            "Flushed %d rows → %s; committed offsets: %s",
            len(rows), self._table, {str(tp): off + 1 for tp, off in offsets.items()},
        )

    async def _run(self) -> None:
        assert self._consumer is not None
        buf: list[_Buffered] = []
        last_flush = asyncio.get_event_loop().time()
        timeout_ms = int(self._settings.batch_timeout_s * 1000)
        try:
            while not self._stop_event.is_set():
                # getmany ждёт до timeout_ms; ловим до batch_size за раз.
                batches = await self._consumer.getmany(
                    timeout_ms=timeout_ms,
                    max_records=self._settings.batch_size,
                )
                for tp, msgs in batches.items():
                    for msg in msgs:
                        try:
                            row = self._parse(msg.value)
                        except Exception:  # noqa: BLE001
                            logger.exception(
                                "Bad message in %s at %s:%s, skipping",
                                self._topic, tp, msg.offset,
                            )
                            continue
                        buf.append(_Buffered(row=row, tp=tp, offset=msg.offset))

                now = asyncio.get_event_loop().time()
                if (
                    len(buf) >= self._settings.batch_size
                    or (buf and (now - last_flush) >= self._settings.batch_timeout_s)
                ):
                    await self._flush(buf)
                    buf = []
                    last_flush = now
        finally:
            # При штатной остановке — последний flush.
            try:
                await self._flush(buf)
            except Exception:  # noqa: BLE001
                logger.exception("Final flush failed for topic=%s", self._topic)


# --- парсеры конкретных топиков ---


def _parse_message_envelope(value: dict[str, Any]) -> list[Any]:
    """Пытаемся принять и «конверт» (Envelope/payload), и «плоское» сообщение.

    Контракт по `messaging/README.md` — это Envelope с payload, но если
    продьюсер по какой-то причине шлёт плоский JSON (легко в тестах),
    тоже принимаем.
    """
    payload = value.get("payload", value)
    metric = MessageMetric.model_validate(payload)
    return _message_row(metric)


def _parse_price_envelope(value: dict[str, Any]) -> list[Any]:
    payload = value.get("payload", value)
    metric = PriceMetric.model_validate(payload)
    return _price_row(metric)


def make_messages_consumer(settings: Settings, ch: ClickHouseClient) -> BaseBatchingConsumer:
    return BaseBatchingConsumer(
        settings=settings,
        ch=ch,
        topic=settings.kafka_topic_messages,
        group_id=settings.kafka_group_messages,
        table=settings.table_messages,
        columns=_MESSAGE_COLUMNS,
        payload_parser=_parse_message_envelope,
    )


def make_prices_consumer(settings: Settings, ch: ClickHouseClient) -> BaseBatchingConsumer:
    return BaseBatchingConsumer(
        settings=settings,
        ch=ch,
        topic=settings.kafka_topic_prices,
        group_id=settings.kafka_group_prices,
        table=settings.table_prices,
        columns=_PRICE_COLUMNS,
        payload_parser=_parse_price_envelope,
    )


__all__ = [
    "BaseBatchingConsumer",
    "make_messages_consumer",
    "make_prices_consumer",
]

# silence linter for unused Envelope import (нужен как часть публичного API файла)
_ = Envelope
_ = datetime
