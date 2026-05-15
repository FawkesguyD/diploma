"""Виджет 1.1 — топ недооценённых объектов (ad-hoc на events_prices).

В отличие от остальных эндпоинтов, здесь нет MV: выборка маленькая
(≤ 100 строк) и редко меняется, поэтому считается «на лету» поверх
`events_prices` с `FINAL` для актуального состояния модели по объекту.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from metrics.api._common import cached, get_cache, get_ch, iso, normalize_period
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards/objects", tags=["dashboards", "objects"])


@router.get("/top-undervalued")
async def top_undervalued(
    city: str = Query(default="Moscow"),
    district: str | None = Query(default=None),
    object_kind: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=7)

    sql = """
    SELECT
        object_id,
        channel_site,
        city,
        district_slug,
        object_kind,
        rooms,
        area,
        price_real,
        price_predicted,
        deviation_abs,
        deviation_pct,
        model_version,
        event_time
    FROM events_prices FINAL
    WHERE event_time >= {since:DateTime}
      AND event_time <  {until:DateTime}
      AND is_undervalued = 1
      AND ({city:String} = '' OR city = {city:String})
      AND ({district:String} = '' OR district_slug = {district:String})
      AND ({kind:String} = '' OR object_kind = {kind:String})
    ORDER BY deviation_pct ASC
    LIMIT {limit:UInt32}
    """
    params = {
        "since": since,
        "until": until,
        "city": city,
        "district": district or "",
        "kind": object_kind or "",
        "limit": limit,
    }

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "object_id": r["object_id"],
                "channel_site": r["channel_site"],
                "city": r["city"],
                "district_slug": r["district_slug"],
                "object_kind": r["object_kind"],
                "rooms": int(r["rooms"] or 0),
                "area": float(r["area"] or 0),
                "price_real": float(r["price_real"] or 0),
                "price_predicted": float(r["price_predicted"] or 0),
                "deviation_abs": float(r["deviation_abs"] or 0),
                "deviation_pct": float(r["deviation_pct"] or 0),
                "model_version": r["model_version"],
                "event_time": iso(r["event_time"]) if isinstance(r["event_time"], datetime) else str(r["event_time"]),
            }
            for r in rows
        ]
        return {
            "points": points,
            "meta": {
                "city": city,
                "district": district,
                "object_kind": object_kind,
                "since": iso(since),
                "until": iso(until),
                "limit": limit,
            },
        }

    return await cached(
        cache,
        prefix="objects.top-undervalued",
        params={
            "city": city,
            "district": district or "",
            "kind": object_kind or "",
            "since": iso(since),
            "until": iso(until),
            "limit": limit,
        },
        granularity="hour",
        loader=_load,
    )
