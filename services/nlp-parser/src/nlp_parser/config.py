from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongo_url: str = Field(default="mongodb://localhost:27017", alias="MONGO_URL")
    mongo_db: str = Field(default="diploma", alias="MONGO_INITDB_DATABASE")

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://diploma:diploma@localhost:5432/diploma",
        alias="DATABASE_URL",
    )

    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL")
    kafka_bootstrap: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP")

    jwt_secret: str = Field(default="dev-insecure-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = Field(default=60 * 30, alias="JWT_ACCESS_TTL_SECONDS")

    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")

    exchange_parser: str = "parser.exchange"
    exchange_nlp: str = "nlp.exchange"
    queue_parse_tg: str = "parse.task.tg"
    queue_parse_news: str = "parse.task.news"
    queue_nlp_analyze: str = "nlp.analyze"
    routing_key_parse_tg: str = "parse.task.tg"
    routing_key_parse_news: str = "parse.task.news"
    routing_key_nlp_analyze: str = "nlp.analyze"
    kafka_topic_messages: str = "metrics.messages"

    worker_prefetch: int = Field(default=8, alias="WORKER_PREFETCH")
    enable_worker_on_startup: bool = Field(default=True, alias="ENABLE_WORKER_ON_STARTUP")

    nlp_model_run_id: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        alias="NLP_MODEL_RUN_ID",
    )

    tg_api_id: int | None = Field(default=None, alias="TG_API_ID")
    tg_api_hash: str | None = Field(default=None, alias="TG_API_HASH")
    tg_session: str | None = Field(default=None, alias="TG_SESSION")
    tg_parse_limit: int = Field(default=50, alias="TG_PARSE_LIMIT")

    http_user_agent: str = Field(
        default="AIS-nlp-parser/0.1 (+https://github.com)",
        alias="HTTP_USER_AGENT",
    )
    http_timeout_sec: float = Field(default=15.0, alias="HTTP_TIMEOUT_SEC")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")

    anthropic_base_url: str = Field(
        default="https://aimtr.wellflow.dev/v1", alias="ANTHROPIC_BASE_URL"
    )
    anthropic_auth_token: str = Field(default="", alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_model: str = Field(default="claude-opus-4.7", alias="ANTHROPIC_MODEL")
    trends_window_hours: int = Field(default=168, alias="TRENDS_WINDOW_HOURS")
    trends_min_messages: int = Field(default=5, alias="TRENDS_MIN_MESSAGES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
