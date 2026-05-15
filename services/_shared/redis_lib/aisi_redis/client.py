from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")
    redis_socket_timeout: float = Field(default=1.0, alias="REDIS_SOCKET_TIMEOUT")
    redis_socket_connect_timeout: float = Field(default=1.0, alias="REDIS_SOCKET_CONNECT_TIMEOUT")


_clients: dict[tuple[str, int, int, str | None], Redis] = {}


def get_client(settings: RedisSettings | None = None) -> Redis:
    s = settings or RedisSettings()
    key = (s.redis_host, s.redis_port, s.redis_db, s.redis_password)
    cached = _clients.get(key)
    if cached is not None:
        return cached
    client = Redis(
        host=s.redis_host,
        port=s.redis_port,
        db=s.redis_db,
        password=s.redis_password,
        socket_timeout=s.redis_socket_timeout,
        socket_connect_timeout=s.redis_socket_connect_timeout,
        decode_responses=True,
    )
    _clients[key] = client
    return client

