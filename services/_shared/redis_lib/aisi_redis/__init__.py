"""Общий Redis-слой АИС: dedup + outbound rate-limit. См. ADR-0009."""

from aisi_redis.client import RedisSettings, get_client
from aisi_redis.dedup import is_duplicate
from aisi_redis.ratelimit import acquire_token

__all__ = [
    "RedisSettings",
    "acquire_token",
    "get_client",
    "is_duplicate",
]
