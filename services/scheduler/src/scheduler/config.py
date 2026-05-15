from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    rabbitmq_url: str = Field(..., alias="RABBITMQ_URL")

    exchange_parser: str = "parser.exchange"
    exchange_realestate: str = "realestate.exchange"
    routing_key_parse_tg: str = "parse.task.tg"
    routing_key_parse_news: str = "parse.task.news"
    routing_key_parse_realestate: str = "parse.task.realestate"

    tick_interval_sec: float = Field(default=15.0, alias="SCHEDULER_TICK_SEC")
    batch_limit: int = Field(default=50, alias="SCHEDULER_BATCH_LIMIT")
    http_port: int = Field(default=8000, alias="HTTP_PORT")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
