from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from nlp_parser.parsing import news_stub, telegram_stub

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000020")


def _run(coro):
    return asyncio.run(coro)


def test_telegram_stub_returns_items():
    items = _run(telegram_stub.parse_source(SOURCE_ID))
    assert len(items) >= 3
    for item in items:
        assert item["source_id"] == str(SOURCE_ID)
        assert item["channel_kind"] == "tg"
        assert item["channel_site"] == "t.me"
        assert item["external_id"]
        assert item["text"]
        assert item["lang"] == "ru"
        assert isinstance(item["published_at"], datetime)


def test_telegram_stub_respects_limit():
    items = _run(telegram_stub.parse_source(SOURCE_ID, limit=2))
    assert len(items) == 2


def test_telegram_stub_filters_since():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    items = _run(telegram_stub.parse_source(SOURCE_ID, since=future))
    assert items == []


def test_news_stub_returns_items():
    items = _run(news_stub.parse_source(SOURCE_ID))
    assert len(items) >= 3
    kinds = {it["channel_kind"] for it in items}
    assert kinds <= {"news", "rss", "html"}
    for item in items:
        assert item["source_id"] == str(SOURCE_ID)
        assert item["text"]
        assert item["external_id"]
