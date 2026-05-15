"""Виджеты 3.1 / 3.3 — тематика."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from metrics.api._common import (
    Granularity,
    auto_granularity,
    cached,
    get_cache,
    get_ch,
    iso,
    normalize_period,
)
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards/topics", tags=["dashboards", "topics"])


_BUCKET_FN: dict[Granularity, str] = {
    "hour": "toStartOfHour(hour)",
    "day": "toDate(hour)",
    "week": "toMonday(hour)",
    "month": "toStartOfMonth(hour)",
    "minute": "toStartOfHour(hour)",
}


@router.get("/activity")
async def topics_activity(
    topic: str = Query(..., min_length=1),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    granularity: Granularity | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=7)
    gran: Granularity = granularity or auto_granularity(since, until)
    if gran == "minute":
        gran = "hour"
    bucket = _BUCKET_FN[gran]

    sql = f"""
    SELECT
        {bucket} AS bucket,
        channel_kind,
        sum(messages_total)   AS messages_total,
        sum(messages_non_ad)  AS messages_non_ad,
        avg(sentiment_avg)    AS sentiment_avg
    FROM mv_messages_by_topic_hourly
    WHERE topic_slug = {{topic:String}}
      AND hour >= {{since:DateTime}}
      AND hour <  {{until:DateTime}}
    GROUP BY bucket, channel_kind
    ORDER BY bucket, channel_kind
    """
    params = {"topic": topic, "since": since, "until": until}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "bucket": iso(r["bucket"]) if isinstance(r["bucket"], datetime) else str(r["bucket"]),
                "channel_kind": r["channel_kind"],
                "messages_total": int(r["messages_total"] or 0),
                "messages_non_ad": int(r["messages_non_ad"] or 0),
                "sentiment_avg": float(r["sentiment_avg"] or 0),
            }
            for r in rows
        ]
        return {
            "points": points,
            "meta": {
                "topic": topic,
                "since": iso(since),
                "until": iso(until),
                "granularity": gran,
            },
        }

    return await cached(
        cache,
        prefix="topics.activity",
        params={"topic": topic, "since": iso(since), "until": iso(until), "g": gran},
        granularity=gran,
        loader=_load,
    )


@router.get("/cooccurrence")
async def topics_cooccurrence(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=30)
    if limit > 2000:
        raise HTTPException(status_code=400, detail="limit too large")

    sql = """
    SELECT
        topic_a,
        topic_b,
        sum(cooccurrence_count) AS weight
    FROM mv_topic_cooccurrence_daily
    WHERE day >= toDate({since:DateTime})
      AND day <= toDate({until:DateTime})
    GROUP BY topic_a, topic_b
    ORDER BY weight DESC
    LIMIT {limit:UInt32}
    """
    params = {"since": since, "until": until, "limit": limit}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        return {
            "points": [
                {
                    "topic_a": r["topic_a"],
                    "topic_b": r["topic_b"],
                    "weight": int(r["weight"] or 0),
                }
                for r in rows
            ],
            "meta": {"since": iso(since), "until": iso(until), "limit": limit},
        }

    return await cached(
        cache,
        prefix="topics.cooccurrence",
        params={"since": iso(since), "until": iso(until), "limit": limit},
        granularity="day",
        loader=_load,
    )
