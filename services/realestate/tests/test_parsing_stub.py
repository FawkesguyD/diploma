from __future__ import annotations

import asyncio
from uuid import UUID

from realestate.parsing import parse_source

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000020")


def _run(coro):
    return asyncio.run(coro)


def test_stub_returns_listings_without_filters():
    items = _run(parse_source(SOURCE_ID, None))
    assert len(items) >= 3
    for item in items:
        assert item["source_id"] == SOURCE_ID
        assert item["external_id"]
        assert item["channel_site"]
        assert item["object_kind"] == "residential"
        assert item["status"] == "active"
        assert "price" in item["listing"]
        assert item["listing"]["currency"] == "RUB"


def test_stub_filters_by_city_and_rooms():
    items = _run(parse_source(SOURCE_ID, {"city": "Moscow", "rooms": [2]}))
    assert len(items) >= 1
    for item in items:
        assert item["listing"]["address"]["city"] == "Moscow"
        assert item["listing"]["rooms"] == 2


def test_stub_filters_by_price_max():
    items = _run(parse_source(SOURCE_ID, {"price_max": 10_000_000}))
    assert len(items) >= 1
    for item in items:
        assert item["listing"]["price"] <= 10_000_000


def test_stub_unknown_city_returns_empty():
    items = _run(parse_source(SOURCE_ID, {"city": "Atlantis"}))
    assert items == []
