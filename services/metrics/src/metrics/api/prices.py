"""Виджеты 2.1 / 2.2 / 2.3 — цены."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

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

router = APIRouter(prefix="/api/dashboards/prices", tags=["dashboards", "prices"])


_TIMESERIES_BUCKET_FN: dict[Granularity, str] = {
    "day": "toDate(day)",
    "week": "toMonday(day)",
    "month": "toStartOfMonth(day)",
    "hour": "toDate(day)",      # MV — daily, повышаем до day
    "minute": "toDate(day)",
}


@router.get("/timeseries")
async def prices_timeseries(
    city: str = Query(default="Moscow"),
    district: list[str] | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    granularity: Granularity | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=90)
    gran: Granularity = granularity or auto_granularity(since, until)
    if gran in ("minute", "hour"):
        gran = "day"
    bucket = _TIMESERIES_BUCKET_FN[gran]

    where = ["day >= toDate({since:DateTime})", "day < toDate({until:DateTime})", "city = {city:String}"]
    params: dict[str, Any] = {"since": since, "until": until, "city": city}
    if district:
        where.append("district_slug IN {districts:Array(String)}")
        params["districts"] = list(district)

    sql = f"""
    SELECT
        {bucket} AS bucket,
        district_slug,
        avgMerge(avg_price_per_m2_state)       AS avg_price_per_m2,
        medianMerge(median_price_per_m2_state) AS median_price_per_m2,
        avgMerge(avg_deviation_pct_state)      AS avg_deviation_pct,
        countMerge(listings_seen_state)        AS listings
    FROM mv_prices_timeseries_daily
    WHERE {' AND '.join(where)}
    GROUP BY bucket, district_slug
    ORDER BY bucket, district_slug
    """

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "bucket": iso(r["bucket"]) if isinstance(r["bucket"], datetime) else str(r["bucket"]),
                "district_slug": r["district_slug"],
                "avg_price_per_m2": float(r["avg_price_per_m2"] or 0),
                "median_price_per_m2": float(r["median_price_per_m2"] or 0),
                "avg_deviation_pct": float(r["avg_deviation_pct"] or 0),
                "listings": int(r["listings"] or 0),
            }
            for r in rows
        ]
        return {
            "points": points,
            "meta": {
                "city": city,
                "districts": district or [],
                "since": iso(since),
                "until": iso(until),
                "granularity": gran,
            },
        }

    return await cached(
        cache,
        prefix="prices.timeseries",
        params={
            "city": city,
            "districts": district or [],
            "since": iso(since),
            "until": iso(until),
            "g": gran,
        },
        granularity=gran,
        loader=_load,
    )


@router.get("/distribution")
async def prices_distribution(
    city: str = Query(default="Moscow"),
    month: str | None = Query(
        default=None, description="ISO-дата начала месяца, напр. 2026-05-01. Иначе — текущий месяц."
    ),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    sql = """
    SELECT
        rooms,
        quantilesMerge(0.25, 0.5, 0.75, 0.9)(price_per_m2_quantiles_state) AS q,
        countMerge(listings_state) AS listings
    FROM mv_price_distribution_by_rooms_monthly
    WHERE city = {city:String}
      AND month = ({month:String} = '' ? toStartOfMonth(now()) : toStartOfMonth(toDate({month:String})))
    GROUP BY rooms
    ORDER BY rooms
    """
    params = {"city": city, "month": month or ""}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = []
        for r in rows:
            q = list(r["q"] or [])
            while len(q) < 4:
                q.append(0.0)
            points.append({
                "rooms": int(r["rooms"]),
                "p25": float(q[0]),
                "p50": float(q[1]),
                "p75": float(q[2]),
                "p90": float(q[3]),
                "listings": int(r["listings"] or 0),
            })
        return {
            "points": points,
            "meta": {"city": city, "month": month},
        }

    return await cached(
        cache,
        prefix="prices.distribution",
        params={"city": city, "month": month or ""},
        granularity="month",
        loader=_load,
    )


@router.get("/by-district")
async def prices_by_district(
    city: str = Query(default="Moscow"),
    month: str | None = Query(default=None, description="ISO-дата начала месяца."),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    sql = """
    SELECT
        district_slug,
        avgMerge(avg_price_per_m2_state)  AS avg_price_per_m2,
        countMerge(listings_seen_state)   AS listings
    FROM mv_prices_timeseries_daily
    WHERE city = {city:String}
      AND day >= toStartOfMonth(({month:String} = '' ? toDate(now()) : toDate({month:String})))
      AND day <  toStartOfMonth(({month:String} = '' ? toDate(now()) : toDate({month:String}))) + INTERVAL 1 MONTH
    GROUP BY district_slug
    ORDER BY avg_price_per_m2 DESC
    """
    params = {"city": city, "month": month or ""}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = [
            {
                "district_slug": r["district_slug"],
                "avg_price_per_m2": float(r["avg_price_per_m2"] or 0),
                "listings": int(r["listings"] or 0),
            }
            for r in rows
        ]
        return {"points": points, "meta": {"city": city, "month": month}}

    return await cached(
        cache,
        prefix="prices.by-district",
        params={"city": city, "month": month or ""},
        granularity="month",
        loader=_load,
    )


# silence linter unused import (Literal не используется)
_ = Literal
