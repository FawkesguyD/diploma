"""Конфиг сервиса realestate. Читается из env (см. docker-compose.yml корня)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- infra ---
    mongo_url: str = Field(default="mongodb://localhost:27017", alias="MONGO_URL")
    mongo_db: str = Field(default="diploma", alias="MONGO_INITDB_DATABASE")

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://diploma:diploma@localhost:5432/diploma",
        alias="DATABASE_URL",
    )

    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL")
    kafka_bootstrap: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP")

    minio_endpoint: str = Field(default="http://localhost:9100", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="diploma", alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="diplomadiploma", alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="models", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # --- domain ---
    model_kind: str = Field(default="realestate_price", alias="MODEL_KIND")
    module_name: str = Field(default="realestate", alias="MODULE_NAME")

    # --- queues ---
    exchange_realestate: str = "realestate.exchange"
    exchange_parser: str = "parser.exchange"
    queue_score: str = "realestate.score"
    queue_rank: str = "realestate.rank"
    queue_parse: str = "parse.task.realestate"
    routing_key_score: str = "realestate.score"
    routing_key_rank: str = "realestate.rank"
    kafka_topic_prices: str = "metrics.prices"

    # --- behaviour ---
    rank_threshold: int = Field(default=10, alias="RANK_THRESHOLD")  # auto-rank if batch >= N
    worker_prefetch: int = Field(default=8, alias="WORKER_PREFETCH")
    enable_worker_on_startup: bool = Field(default=True, alias="ENABLE_WORKER_ON_STARTUP")

    def postgres_sync_dsn(self) -> str:
        """psycopg-вариант DSN, если понадобится Alembic / sync-код."""
        return self.postgres_dsn.replace("+asyncpg", "+psycopg")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
