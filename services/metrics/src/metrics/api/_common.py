"""Общие зависимости и хелперы FastAPI-роутов /api/dashboards/*."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal

from fastapi import HTTPException, Request

from metrics.cache import TTLCache, make_key, ttl_for_granularity
from metrics.clickhouse import ClickHouseClient

Granularity = Literal["minute", "hour", "day", "week", "month"]


def get_ch(request: Request) -> ClickHouseClient:
    ch: ClickHouseClient | None = getattr(request.app.state, "ch", None)
    if ch is None:
        raise HTTPException(status_code=503, detail="ClickHouse client is not initialised")
    return ch


def get_cache(request: Request) -> TTLCache:
    return request.app.state.cache  # type: ignore[no-any-return]


def auto_granularity(since: datetime, until: datetime) -> Granularity:
    """Подбираем гранулярность по длине периода (см. dashboards.md)."""
    delta = until - since
    if delta <= timedelta(days=1):
        return "hour"
    if delta <= timedelta(days=7):
        return "hour"
    if delta <= timedelta(days=90):
        return "day"
    if delta <= timedelta(days=365):
        return "week"
    return "month"


def default_period(days: int = 7) -> tuple[datetime, datetime]:
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    return since, until


def normalize_period(
    since: datetime | None,
    until: datetime | None,
    default_days: int = 7,
) -> tuple[datetime, datetime]:
    if since is None or until is None:
        s, u = default_period(default_days)
        return since or s, until or u
    if since >= until:
        raise HTTPException(status_code=400, detail="since must be < until")
    return since, until


async def cached(
    cache: TTLCache,
    prefix: str,
    params: dict[str, Any],
    granularity: Granularity | None,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    key = make_key(prefix, params)
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = await loader()
    ttl = ttl_for_granularity(granularity) if granularity else 300
    cache.set(key, value, ttl)
    return value


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
