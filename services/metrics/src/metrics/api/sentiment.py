"""Виджет 3.2 — тональность по районам."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from metrics.api._common import cached, get_cache, get_ch, iso, normalize_period
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards/sentiment", tags=["dashboards", "sentiment"])


@router.get("/by-district")
async def sentiment_by_district(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=30)

    sql = """
    SELECT
        district_slug,
        sum(messages_total) AS messages_total,
        sum(pos_count)      AS pos_count,
        sum(neu_count)      AS neu_count,
        sum(neg_count)      AS neg_count,
        avg(sentiment_avg)  AS sentiment_avg
    FROM mv_sentiment_by_district_daily
    WHERE day >= toDate({since:DateTime})
      AND day <  toDate({until:DateTime})
    GROUP BY district_slug
    ORDER BY sentiment_avg DESC
    """
    params = {"since": since, "until": until}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "district_slug": r["district_slug"],
                "messages_total": int(r["messages_total"] or 0),
                "pos_count": int(r["pos_count"] or 0),
                "neu_count": int(r["neu_count"] or 0),
                "neg_count": int(r["neg_count"] or 0),
                "sentiment_avg": float(r["sentiment_avg"] or 0),
            }
            for r in rows
        ]
        return {"points": points, "meta": {"since": iso(since), "until": iso(until)}}

    return await cached(
        cache,
        prefix="sentiment.by-district",
        params={"since": iso(since), "until": iso(until)},
        granularity="day",
        loader=_load,
    )
