"""Конфиг сервиса metrics. Читается из env (см. docker-compose.yml корня)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- ClickHouse ---
    # Префиксованный URL вида http://user:pass@clickhouse:8123/db ИЛИ
    # отдельные поля (хост/порт/credentials берутся через переменные).
    clickhouse_url: str = Field(
        default="http://default:@localhost:8123/default", alias="CLICKHOUSE_URL"
    )
    clickhouse_user: str | None = Field(default=None, alias="CLICKHOUSE_USER")
    clickhouse_password: str | None = Field(default=None, alias="CLICKHOUSE_PASSWORD")
    clickhouse_db: str | None = Field(default=None, alias="CLICKHOUSE_DB")

    # --- Kafka ---
    kafka_bootstrap: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP")
    kafka_topic_messages: str = "metrics.messages"
    kafka_topic_prices: str = "metrics.prices"
    kafka_group_messages: str = "metrics-ch-messages"
    kafka_group_prices: str = "metrics-ch-prices"

    # --- ClickHouse target tables ---
    table_messages: str = "events_messages"
    table_prices: str = "events_prices"

    # --- Consumer batching ---
    batch_size: int = Field(default=500, alias="BATCH_SIZE")
    batch_timeout_s: float = Field(default=5.0, alias="BATCH_TIMEOUT_S")

    # --- Behaviour ---
    enable_consumers_on_startup: bool = Field(default=True, alias="ENABLE_CONSUMERS_ON_STARTUP")

    # --- Cache ---
    cache_max_entries: int = Field(default=512, alias="CACHE_MAX_ENTRIES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
