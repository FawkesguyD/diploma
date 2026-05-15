"""ClickHouse-клиент: пул соединений + батч-инсёрты в `events_*`.

Подключение — через `clickhouse-connect` (HTTP). У него есть и async-API
(`get_async_client`), но фактически он делает синхронные HTTP-запросы под
капотом. Для нашего объёма (десятки RPS на /api/dashboards/* + батчи раз
в несколько секунд) этого хватает.

Здесь только тонкая обёртка:
* парсинг URL → host/port/credentials/db;
* `query(sql, params)` → `[dict, ...]` для API-ручек;
* `insert_rows(table, columns, rows)` для Kafka-консьюмера.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence
from urllib.parse import urlparse

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from metrics.config import Settings

logger = logging.getLogger(__name__)


def _parse_url(settings: Settings) -> dict[str, Any]:
    """Достаёт host/port/user/password/db из `CLICKHOUSE_URL` либо из явных полей."""
    u = urlparse(settings.clickhouse_url)
    host = u.hostname or "localhost"
    port = u.port or 8123
    user = settings.clickhouse_user or u.username or "default"
    password = settings.clickhouse_password or u.password or ""
    database = settings.clickhouse_db or (u.path.lstrip("/") if u.path else None) or "default"
    return {
        "host": host,
        "port": port,
        "username": user,
        "password": password,
        "database": database,
        "interface": "http" if (u.scheme or "http") in ("http", "https") else "http",
        "secure": (u.scheme == "https"),
    }


class ClickHouseClient:
    """Тонкая обёртка над `clickhouse_connect.AsyncClient`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        params = _parse_url(self._settings)
        logger.info(
            "Connecting to ClickHouse host=%s port=%s db=%s user=%s",
            params["host"], params["port"], params["database"], params["username"],
        )
        self._client = await clickhouse_connect.get_async_client(**params)

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                logger.exception("ClickHouse close() failed")
            self._client = None

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            raise RuntimeError("ClickHouseClient not started")
        return self._client

    async def ping(self) -> bool:
        try:
            await self.client.command("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Возвращает список словарей `column → value`."""
        result = await self.client.query(sql, parameters=params or {})
        cols = result.column_names
        return [dict(zip(cols, row)) for row in result.result_rows]

    async def insert_rows(
        self,
        table: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> None:
        if not rows:
            return
        await self.client.insert(table, rows, column_names=list(columns))
