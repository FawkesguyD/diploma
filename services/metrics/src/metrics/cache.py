"""In-memory LRU-кэш с TTL для ответов /api/dashboards/*.

Простой OrderedDict-LRU. Зачем не aiocache/Redis: для дипломного объёма
данных RPS низкий, кэш переживёт перезапуск нормально (ClickHouse ответит
заново). При нескольких репликах metrics-сервиса каждая будет иметь
собственный кэш — для дашбордов это допустимо.

TTL по `dashboards.md`: TTL = granularity / 2 (для часовых данных — 30 мин).
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

_GRANULARITY_TTL_S: dict[str, float] = {
    "minute": 30,
    "hour": 30 * 60,
    "day": 12 * 3600,
    "week": 3.5 * 24 * 3600,
    "month": 15 * 24 * 3600,
}


def ttl_for_granularity(granularity: str) -> float:
    return _GRANULARITY_TTL_S.get(granularity, 5 * 60)


class TTLCache:
    """Ассоциация key → (expires_at, value). Эвикция — LRU."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_s: float) -> None:
        self._data[key] = (time.monotonic() + ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


def make_key(prefix: str, params: dict[str, Any]) -> str:
    parts = [prefix]
    for k in sorted(params):
        v = params[k]
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            v = ",".join(map(str, v))
        parts.append(f"{k}={v}")
    return "|".join(parts)
