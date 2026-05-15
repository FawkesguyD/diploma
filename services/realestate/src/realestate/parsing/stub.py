"""Stub-парсер площадок недвижимости.

Возвращает детерминированный набор объявлений в формате коллекции
``objects`` (см. ``docs/design/databases/mongo.md``). Реальные адаптеры
CIAN/Avito/DomClick подключаются как отдельные реализации `parse_source`
позже — здесь только мок для прохождения end-to-end пайплайна
parse → score → rank → metrics на dev-стеке.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

_FIXTURE: list[dict[str, Any]] = [
    {
        "external_id": "stub:cian:101",
        "channel_site": "cian.ru",
        "url": "https://cian.ru/sale/flat/101",
        "object_kind": "residential",
        "listing": {
            "price": 12_500_000,
            "currency": "RUB",
            "area": 52.4,
            "rooms": 2,
            "floor": 7,
            "total_floors": 16,
            "year_built": 2008,
            "address": {
                "raw": "Москва, Пресненская наб., 12",
                "city": "Moscow",
                "district_slug": "presnenskiy",
                "lat": 55.760,
                "lon": 37.580,
            },
            "features": ["balcony", "renovation_eu"],
        },
    },
    {
        "external_id": "stub:cian:102",
        "channel_site": "cian.ru",
        "url": "https://cian.ru/sale/flat/102",
        "object_kind": "residential",
        "listing": {
            "price": 9_900_000,
            "currency": "RUB",
            "area": 38.0,
            "rooms": 1,
            "floor": 3,
            "total_floors": 9,
            "year_built": 1985,
            "address": {
                "raw": "Москва, Ленинский просп., 50",
                "city": "Moscow",
                "district_slug": "gagarinskiy",
                "lat": 55.711,
                "lon": 37.580,
            },
            "features": [],
        },
    },
    {
        "external_id": "stub:avito:201",
        "channel_site": "avito.ru",
        "url": "https://avito.ru/moskva/kvartiry/201",
        "object_kind": "residential",
        "listing": {
            "price": 17_000_000,
            "currency": "RUB",
            "area": 76.0,
            "rooms": 3,
            "floor": 12,
            "total_floors": 22,
            "year_built": 2018,
            "address": {
                "raw": "Москва, ул. Мосфильмовская, 88",
                "city": "Moscow",
                "district_slug": "ramenki",
                "lat": 55.726,
                "lon": 37.516,
            },
            "features": ["concierge", "parking"],
        },
    },
    {
        "external_id": "stub:domclick:301",
        "channel_site": "domclick.ru",
        "url": "https://domclick.ru/object/301",
        "object_kind": "residential",
        "listing": {
            "price": 6_300_000,
            "currency": "RUB",
            "area": 41.0,
            "rooms": 2,
            "floor": 5,
            "total_floors": 10,
            "year_built": 1972,
            "address": {
                "raw": "Санкт-Петербург, пр. Просвещения, 30",
                "city": "Saint-Petersburg",
                "district_slug": "vyborgskiy",
                "lat": 60.038,
                "lon": 30.343,
            },
            "features": [],
        },
    },
    {
        "external_id": "stub:cian:103",
        "channel_site": "cian.ru",
        "url": "https://cian.ru/sale/flat/103",
        "object_kind": "residential",
        "listing": {
            "price": 13_500_000,
            "currency": "RUB",
            "area": 60.0,
            "rooms": 2,
            "floor": 14,
            "total_floors": 25,
            "year_built": 2021,
            "address": {
                "raw": "Москва, ул. Беговая, 4",
                "city": "Moscow",
                "district_slug": "begovoy",
                "lat": 55.781,
                "lon": 37.553,
            },
            "features": ["concierge"],
        },
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _matches(listing: dict[str, Any], filters: dict[str, Any]) -> bool:
    address = listing.get("listing", {}).get("address", {})
    listing_block = listing.get("listing", {})

    city = filters.get("city")
    if city is not None and address.get("city") != city:
        return False

    rooms_filter = filters.get("rooms")
    if rooms_filter is not None:
        rooms_value = listing_block.get("rooms")
        if rooms_value is None or rooms_value not in rooms_filter:
            return False

    price_max = filters.get("price_max")
    if price_max is not None:
        price_value = listing_block.get("price")
        if price_value is None or price_value > price_max:
            return False

    return True


async def parse_source(
    source_id: UUID, filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Вернуть список mock-объявлений как dict'ов, готовых для upsert в Mongo."""
    now = _now()
    items: list[dict[str, Any]] = []
    for fixture in _FIXTURE:
        if filters and not _matches(fixture, filters):
            continue
        items.append(
            {
                "source_id": str(source_id),
                "external_id": fixture["external_id"],
                "channel_site": fixture["channel_site"],
                "object_kind": fixture["object_kind"],
                "url": fixture["url"],
                "listing": fixture["listing"],
                "fetched_at": now,
                "published_at": now,
                "status": "active",
                "history": [],
                "raw": fixture,
            }
        )
    return items


__all__ = ["parse_source"]
