from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

_FIXTURES: list[dict[str, Any]] = [
    {
        "external_id": "rbc:news:1001",
        "channel_kind": "news",
        "channel_site": "rbc.ru",
        "url": "https://rbc.ru/realty/2026/05/14/1001",
        "author": {"name": "РБК Недвижимость", "handle": "rbc.ru"},
        "text": (
            "В Москве за апрель введено 1.2 млн м² жилья. "
            "Лидером по объёму ввода стал Раменский район."
        ),
        "lang": "ru",
    },
    {
        "external_id": "kommersant:news:1002",
        "channel_kind": "news",
        "channel_site": "kommersant.ru",
        "url": "https://kommersant.ru/doc/1002",
        "author": {"name": "Коммерсантъ", "handle": "kommersant.ru"},
        "text": (
            "Capital Group объявил о запуске нового проекта на Беговой. "
            "Старт продаж — июнь 2026."
        ),
        "lang": "ru",
    },
    {
        "external_id": "vedomosti:news:1003",
        "channel_kind": "news",
        "channel_site": "vedomosti.ru",
        "url": "https://vedomosti.ru/realty/1003",
        "author": {"name": "Ведомости", "handle": "vedomosti.ru"},
        "text": (
            "Аналитики ЦИАН отмечают позитивную динамику цен на новостройки "
            "в Гагаринском районе Москвы. Рост за квартал — 4.5%."
        ),
        "lang": "ru",
    },
    {
        "external_id": "rss:realty_press:1004",
        "channel_kind": "rss",
        "channel_site": "realty.press",
        "url": "https://realty.press/feed/1004",
        "author": {"name": "Realty Press", "handle": "realty.press"},
        "text": (
            "Рынок коммерческой недвижимости Санкт-Петербурга демонстрирует "
            "снижение арендных ставок в Выборгском районе."
        ),
        "lang": "ru",
    },
    {
        "external_id": "html:dev_blog:1005",
        "channel_kind": "html",
        "channel_site": "dev-blog.example",
        "url": "https://dev-blog.example/post/1005",
        "author": {"name": "Dev Blog", "handle": "dev-blog.example"},
        "text": (
            "Реклама: Купите квартиру в новостройке со скидкой! "
            "Только сегодня — выгодные условия от застройщика."
        ),
        "lang": "ru",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def parse_source(
    source_id: UUID,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    now = _now()
    items: list[dict[str, Any]] = []
    for idx, fx in enumerate(_FIXTURES):
        published_at = now - timedelta(minutes=idx * 7)
        if since is not None and published_at < since:
            continue
        items.append(
            {
                "source_id": str(source_id),
                "channel_kind": fx["channel_kind"],
                "channel_site": fx["channel_site"],
                "external_id": fx["external_id"],
                "url": fx["url"],
                "author": fx["author"],
                "published_at": published_at,
                "fetched_at": now,
                "text": fx["text"],
                "lang": fx["lang"],
                "media": [],
                "raw_meta": {},
            }
        )
    return items


__all__ = ["parse_source"]
