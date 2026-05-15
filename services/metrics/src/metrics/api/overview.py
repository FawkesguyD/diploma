"""Виджет 1.2 — KPI «активность рынка за период».

`mv_district_activity_daily` даёт новые объекты и долю недооценённых;
`mv_messages_by_topic_hourly` — поток сообщений (минус реклама) и
среднюю тональность. Период по умолчанию — последние 7 дней;
дополнительно считаем тренд vs предыдущий период такой же длины.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from metrics.api._common import (
    cached,
    get_cache,
    get_ch,
    iso,
    normalize_period,
)
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


_OBJECTS_SQL = """
SELECT
    sum(listings_new)        AS listings_new,
    sum(undervalued_count)   AS undervalued
FROM mv_district_activity_daily
WHERE day >= toDate({since:DateTime}) AND day < toDate({until:DateTime})
  AND ({city:String} = '' OR city = {city:String})
"""

_MESSAGES_SQL = """
SELECT
    sum(messages_non_ad)  AS msg_non_ad,
    avg(sentiment_avg)    AS sentiment_avg
FROM mv_messages_by_topic_hourly
WHERE hour >= {since:DateTime} AND hour < {until:DateTime}
"""


async def _kpi(ch: ClickHouseClient, since: datetime, until: datetime, city: str) -> dict[str, Any]:
    params = {"since": since, "until": until, "city": city}
    objects = await ch.query(_OBJECTS_SQL, params)
    messages = await ch.query(_MESSAGES_SQL, params)
    o = objects[0] if objects else {}
    m = messages[0] if messages else {}
    return {
        "listings_new": int(o.get("listings_new") or 0),
        "undervalued": int(o.get("undervalued") or 0),
        "messages_non_ad": int(m.get("msg_non_ad") or 0),
        "sentiment_avg": float(m.get("sentiment_avg") or 0.0),
    }


@router.get("/overview")
async def overview(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    city: str = Query(default=""),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=7)
    delta = until - since
    prev_since = since - delta
    prev_until = since

    async def _load() -> dict[str, Any]:
        current = await _kpi(ch, since, until, city)
        previous = await _kpi(ch, prev_since, prev_until, city)
        return {
            "kpi": current,
            "previous": previous,
            "meta": {
                "since": iso(since),
                "until": iso(until),
                "city": city or None,
            },
        }

    return await cached(
        cache,
        prefix="overview",
        params={"since": iso(since), "until": iso(until), "city": city},
        granularity="day",
        loader=_load,
    )
