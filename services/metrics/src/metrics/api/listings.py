"""Виджет 5.1 — поток объектов по площадкам."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from metrics.api._common import cached, get_cache, get_ch, iso, normalize_period
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards/listings", tags=["dashboards", "listings"])


@router.get("/by-channel")
async def listings_by_channel(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    object_kind: str | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=30)

    sql = """
    SELECT
        day,
        channel_site,
        object_kind,
        sum(listings_new)        AS listings_new,
        avg(avg_price_per_m2)    AS avg_price_per_m2,
        sum(undervalued_count)   AS undervalued
    FROM mv_listings_by_channel_daily
    WHERE day >= toDate({since:DateTime})
      AND day <= toDate({until:DateTime})
      AND ({kind:String} = '' OR object_kind = {kind:String})
    GROUP BY day, channel_site, object_kind
    ORDER BY day, channel_site
    """
    params = {"since": since, "until": until, "kind": object_kind or ""}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "day": iso(r["day"]) if isinstance(r["day"], datetime) else str(r["day"]),
                "channel_site": r["channel_site"],
                "object_kind": r["object_kind"],
                "listings_new": int(r["listings_new"] or 0),
                "avg_price_per_m2": float(r["avg_price_per_m2"] or 0),
                "undervalued": int(r["undervalued"] or 0),
            }
            for r in rows
        ]
        return {
            "points": points,
            "meta": {
                "since": iso(since),
                "until": iso(until),
                "object_kind": object_kind,
            },
        }

    return await cached(
        cache,
        prefix="listings.by-channel",
        params={"since": iso(since), "until": iso(until), "kind": object_kind or ""},
        granularity="day",
        loader=_load,
    )
