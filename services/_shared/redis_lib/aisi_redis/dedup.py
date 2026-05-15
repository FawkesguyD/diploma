from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

DEDUP_TTL_INGEST = 86400
DEDUP_TTL_PROCESS = 3600


async def is_duplicate(
    client: Redis,
    domain: str,
    *,
    site: str | None = None,
    external_id: str | None = None,
    object_id: str | None = None,
    ttl: int = DEDUP_TTL_INGEST,
) -> bool:
    """SET NX EX. True → дубль (skip). False → новое (proceed).

    Fail-open: при недоступности Redis возвращает False — дубли ловит upsert БД.
    """
    if site is not None and external_id is not None:
        key = f"dedup:{domain}:{site}:{external_id}"
    elif object_id is not None:
        key = f"dedup:{domain}:{object_id}"
    else:
        raise ValueError("Either (site, external_id) or object_id must be provided")

    try:
        was_set = await client.set(key, "1", ex=ttl, nx=True)
        return was_set is None
    except RedisError as exc:
        log.warning("redis_unavailable_dedup_fallback key=%s err=%s", key, exc)
        return False
