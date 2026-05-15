from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

_FIXTURES: list[dict[str, Any]] = [
    {
        "external_id": "tg:badaevsky:101",
        "channel_kind": "tg",
        "channel_site": "t.me",
        "url": "https://t.me/badaevsky/101",
        "author": {"name": "Бадаевский квартал", "handle": "@badaevsky"},
        "text": (
            "Старт продаж третьей очереди ЖК «Бадаевский». "
            "Цена от 350 тыс ₽/м². Ипотека от Сбербанка под 6%."
        ),
        "lang": "ru",
    },
    {
        "external_id": "tg:realty_news:202",
        "channel_kind": "tg",
        "channel_site": "t.me",
        "url": "https://t.me/realty_news/202",
        "author": {"name": "Realty News", "handle": "@realty_news"},
        "text": (
            "ЦБ РФ оставил ключевую ставку на уровне 16%. "
            "Ипотечные программы Capital Group остаются доступны."
        ),
        "lang": "ru",
    },
    {
        "external_id": "tg:moscow_homes:303",
        "channel_kind": "tg",
        "channel_site": "t.me",
        "url": "https://t.me/moscow_homes/303",
        "author": {"name": "Moscow Homes", "handle": "@moscow_homes"},
        "text": (
            "В Пресненском районе зафиксирован рост спроса на двухкомнатные "
            "квартиры. Средняя цена квадратного метра — 420 тыс ₽."
        ),
        "lang": "ru",
    },
    {
        "external_id": "tg:ads_dump:404",
        "channel_kind": "tg",
        "channel_site": "t.me",
        "url": "https://t.me/ads_dump/404",
        "author": {"name": "Ads Dump", "handle": "@ads_dump"},
        "text": (
            "🔥 СКИДКА 50% на курс по инвестициям в недвижимость! "
            "Регистрация по ссылке. Промокод DIPLOM."
        ),
        "lang": "ru",
    },
    {
        "external_id": "tg:spb_realty:505",
        "channel_kind": "tg",
        "channel_site": "t.me",
        "url": "https://t.me/spb_realty/505",
        "author": {"name": "SPB Realty", "handle": "@spb_realty"},
        "text": (
            "Выборгский район Санкт-Петербурга показал снижение цен на "
            "вторичку: -3.2% к прошлому месяцу. Настроение на рынке негативное."
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
    limit: int | None = None,
) -> list[dict[str, Any]]:
    now = _now()
    items: list[dict[str, Any]] = []
    for idx, fx in enumerate(_FIXTURES):
        published_at = now - timedelta(minutes=idx * 5)
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
                "raw_meta": {"views": 1000 + idx * 100, "forwards": idx},
            }
        )
    if limit is not None:
        items = items[:limit]
    return items


__all__ = ["parse_source"]
