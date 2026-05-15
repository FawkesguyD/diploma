from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

WINDOW_SEC = 60
DEFAULT_LIMITS: dict[str, int] = {
    "telegram.org": 100,
    "avito.ru": 30,
    "cian.ru": 30,
    "ria.ru": 60,
    "rbc.ru": 60,
    "default": 30,
}


def limit_for(host: str, overrides: dict[str, int] | None = None) -> int:
    table = {**DEFAULT_LIMITS, **(overrides or {})}
    return table.get(host, table["default"])


async def acquire_token(
    client: Redis,
    host: str,
    max_per_min: int,
    *,
    _depth: int = 0,
) -> None:
    """Fixed-window rate-limit. Блокирует до получения токена.

    Fail-closed: при недоступности Redis sleep 1с — защита от ban'а.
    """
    key = f"ratelimit:src:{host}"
    try:
        cur = await client.incr(key)
        if cur == 1:
            await client.expire(key, WINDOW_SEC)
        if cur > max_per_min:
            wait = await client.ttl(key)
            wait_s = max(int(wait), 1)
            log.info("ratelimit_hit host=%s cur=%s wait=%s", host, cur, wait_s)
            await asyncio.sleep(wait_s)
            if _depth < 5:
                await acquire_token(client, host, max_per_min, _depth=_depth + 1)
    except RedisError as exc:
        log.warning("redis_unavailable_ratelimit_fallback host=%s err=%s", host, exc)
        await asyncio.sleep(1)
