from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from nlp_parser.config import Settings
from nlp_parser.parsing import html as html_adapter
from nlp_parser.parsing import news_stub, rss as rss_adapter, telegram as tg_adapter
from nlp_parser.parsing import telegram_stub


class ParseAdapter(Protocol):
    async def __call__(
        self,
        source_id: UUID,
        *,
        url_or_handle: str,
        settings: Settings,
        config: dict[str, Any] | None,
        since: datetime | None,
        limit: int | None,
    ) -> list[dict[str, Any]]: ...


async def _telegram(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    config: dict[str, Any] | None,
    since: datetime | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    if tg_adapter.is_configured(settings):
        return await tg_adapter.parse_source(
            source_id,
            url_or_handle=url_or_handle,
            settings=settings,
            since=since,
            limit=limit,
        )
    return await telegram_stub.parse_source(source_id, since=since, limit=limit)


async def _rss(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    config: dict[str, Any] | None,
    since: datetime | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    return await rss_adapter.parse_source(
        source_id, url_or_handle=url_or_handle, settings=settings, since=since
    )


async def _html(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    config: dict[str, Any] | None,
    since: datetime | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    return await html_adapter.parse_source(
        source_id,
        url_or_handle=url_or_handle,
        settings=settings,
        config=config,
        since=since,
    )


async def _news_fallback(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    config: dict[str, Any] | None,
    since: datetime | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    if url_or_handle and (url_or_handle.startswith("http://") or url_or_handle.startswith("https://")):
        if url_or_handle.endswith(".xml") or "rss" in url_or_handle.lower() or "feed" in url_or_handle.lower():
            return await rss_adapter.parse_source(
                source_id, url_or_handle=url_or_handle, settings=settings, since=since
            )
        return await html_adapter.parse_source(
            source_id,
            url_or_handle=url_or_handle,
            settings=settings,
            config=config,
            since=since,
        )
    return await news_stub.parse_source(source_id, since=since)


_REGISTRY: dict[str, Callable[..., Awaitable[list[dict[str, Any]]]]] = {
    "tg": _telegram,
    "rss": _rss,
    "html": _html,
    "news": _news_fallback,
}


def get_adapter(kind: str) -> Callable[..., Awaitable[list[dict[str, Any]]]]:
    if kind not in _REGISTRY:
        raise ValueError(f"unknown source kind: {kind}")
    return _REGISTRY[kind]


__all__ = ["get_adapter", "ParseAdapter"]
