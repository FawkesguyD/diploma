"""Виджеты 4.1 / 4.2 — качество модели."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from metrics.api._common import cached, get_cache, get_ch, iso, normalize_period
from metrics.cache import TTLCache
from metrics.clickhouse import ClickHouseClient

router = APIRouter(prefix="/api/dashboards/model-quality", tags=["dashboards", "model"])


@router.get("")
async def model_quality(
    model_version: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=30)

    sql = """
    SELECT
        day,
        model_version,
        countMerge(predictions_state)                 AS predictions,
        avgMerge(mae_pct_state)                       AS mae_pct,
        quantilesMerge(0.5, 0.9)(abs_dev_quantiles_state) AS abs_dev_quantiles,
        sumMerge(undervalued_state)                   AS undervalued
    FROM mv_model_quality_daily
    WHERE day >= toDate({since:DateTime})
      AND day <= toDate({until:DateTime})
      AND ({version:String} = '' OR model_version = {version:String})
    GROUP BY day, model_version
    ORDER BY day, model_version
    """
    params = {"since": since, "until": until, "version": model_version or ""}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = []
        for r in rows:
            q = list(r["abs_dev_quantiles"] or [])
            while len(q) < 2:
                q.append(0.0)
            points.append({
                "day": iso(r["day"]) if isinstance(r["day"], datetime) else str(r["day"]),
                "model_version": r["model_version"],
                "predictions": int(r["predictions"] or 0),
                "mae_pct": float(r["mae_pct"] or 0),
                "abs_dev_p50": float(q[0]),
                "abs_dev_p90": float(q[1]),
                "undervalued": int(r["undervalued"] or 0),
            })
        return {
            "points": points,
            "meta": {
                "model_version": model_version,
                "since": iso(since),
                "until": iso(until),
            },
        }

    return await cached(
        cache,
        prefix="model-quality",
        params={"v": model_version or "", "since": iso(since), "until": iso(until)},
        granularity="day",
        loader=_load,
    )


@router.get("/undervalued-share")
async def undervalued_share(
    model_version: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    ch: ClickHouseClient = Depends(get_ch),
    cache: TTLCache = Depends(get_cache),
) -> dict[str, Any]:
    since, until = normalize_period(since, until, default_days=30)

    # Делим долю недооценённых от модели на общий поток новых объектов в день.
    sql = """
    SELECT
        m.day                                       AS day,
        sumMerge(m.undervalued_state)               AS undervalued,
        any(d.listings_total)                       AS listings_total
    FROM mv_model_quality_daily AS m
    LEFT JOIN (
        SELECT day, sum(listings_new) AS listings_total
        FROM mv_district_activity_daily
        WHERE day >= toDate({since:DateTime}) AND day <= toDate({until:DateTime})
        GROUP BY day
    ) AS d ON d.day = m.day
    WHERE m.day >= toDate({since:DateTime})
      AND m.day <= toDate({until:DateTime})
      AND ({version:String} = '' OR m.model_version = {version:String})
    GROUP BY day
    ORDER BY day
    """
    params = {"since": since, "until": until, "version": model_version or ""}

    async def _load() -> dict[str, Any]:
        rows = await ch.query(sql, params)
        points = []
        for r in rows:
            uv = int(r["undervalued"] or 0)
            total = int(r["listings_total"] or 0)
            share = (uv / total) if total else 0.0
            points.append({
                "day": iso(r["day"]) if isinstance(r["day"], datetime) else str(r["day"]),
                "undervalued": uv,
                "listings_total": total,
                "share": share,
            })
        return {
            "points": points,
            "meta": {
                "model_version": model_version,
                "since": iso(since),
                "until": iso(until),
            },
        }

    return await cached(
        cache,
        prefix="model-quality.undervalued-share",
        params={"v": model_version or "", "since": iso(since), "until": iso(until)},
        granularity="day",
        loader=_load,
    )
