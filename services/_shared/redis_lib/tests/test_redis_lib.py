import asyncio

import pytest
from redis.exceptions import RedisError

from aisi_redis.dedup import DEDUP_TTL_INGEST, is_duplicate
from aisi_redis.ratelimit import WINDOW_SEC, acquire_token, limit_for


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl_map: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> str | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return "OK"

    async def incr(self, key: str) -> int:
        cur = int(self.store.get(key, "0")) + 1
        self.store[key] = str(cur)
        return cur

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttl_map[key] = ttl
        return True

    async def ttl(self, key: str) -> int:
        return self.ttl_map.get(key, -1)


class BrokenRedis(FakeRedis):
    async def set(self, *args, **kwargs):
        raise RedisError("down")

    async def incr(self, key: str) -> int:
        raise RedisError("down")


async def test_dedup_first_call_proceeds_then_blocks() -> None:
    r = FakeRedis()
    assert await is_duplicate(r, "msg", site="tg", external_id="1") is False
    assert await is_duplicate(r, "msg", site="tg", external_id="1") is True


async def test_dedup_distinct_keys() -> None:
    r = FakeRedis()
    assert await is_duplicate(r, "msg", site="tg", external_id="1") is False
    assert await is_duplicate(r, "msg", site="tg", external_id="2") is False


async def test_dedup_object_id_form() -> None:
    r = FakeRedis()
    assert await is_duplicate(r, "annotate", object_id="abc") is False
    assert await is_duplicate(r, "annotate", object_id="abc") is True


async def test_dedup_requires_identifier() -> None:
    r = FakeRedis()
    with pytest.raises(ValueError):
        await is_duplicate(r, "msg")


async def test_dedup_redis_down_fails_open() -> None:
    r = BrokenRedis()
    assert await is_duplicate(r, "msg", site="tg", external_id="1") is False


async def test_dedup_ttl_passed() -> None:
    r = FakeRedis()
    await is_duplicate(r, "msg", site="tg", external_id="1", ttl=DEDUP_TTL_INGEST)
    assert r.ttl_map["dedup:msg:tg:1"] == DEDUP_TTL_INGEST


async def test_ratelimit_first_call_sets_window() -> None:
    r = FakeRedis()
    await acquire_token(r, "avito.ru", 30)
    assert r.store["ratelimit:src:avito.ru"] == "1"
    assert r.ttl_map["ratelimit:src:avito.ru"] == WINDOW_SEC


async def test_ratelimit_blocks_when_exceeded(monkeypatch) -> None:
    r = FakeRedis()
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)
        r.store["ratelimit:src:avito.ru"] = "0"
        r.ttl_map["ratelimit:src:avito.ru"] = WINDOW_SEC

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    for _ in range(2):
        await acquire_token(r, "avito.ru", 1)
    assert sleeps and sleeps[0] >= 1


async def test_ratelimit_redis_down_fails_closed(monkeypatch) -> None:
    r = BrokenRedis()
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await acquire_token(r, "avito.ru", 30)
    assert sleeps == [1]


def test_limit_for_known_and_default() -> None:
    assert limit_for("telegram.org") == 100
    assert limit_for("avito.ru") == 30
    assert limit_for("unknown.example") == 30
    assert limit_for("custom.example", overrides={"custom.example": 5}) == 5
