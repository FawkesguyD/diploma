from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import feedparser
import httpx

from nlp_parser.config import Settings

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_pub_date(entry: dict[str, Any]) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return _now()
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _entry_text(entry: dict[str, Any]) -> str:
    summary = (entry.get("summary") or "").strip()
    content_list = entry.get("content") or []
    body_parts = [c.get("value", "") for c in content_list if isinstance(c, dict)]
    body = "\n".join(p for p in body_parts if p).strip()
    chosen = body or summary
    if not chosen:
        return ""
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(chosen, "lxml").get_text(" ", strip=True)
    except (ImportError, Exception):
        return chosen


def _channel_site_from_link(link: str | None) -> str:
    if not link:
        return "unknown"
    from urllib.parse import urlparse

    host = urlparse(link).netloc.lower()
    return host[4:] if host.startswith("www.") else host or "unknown"


async def parse_source(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    headers = {"User-Agent": settings.http_user_agent}
    async with httpx.AsyncClient(timeout=settings.http_timeout_sec, headers=headers, follow_redirects=True) as client:
        response = await client.get(url_or_handle)
        response.raise_for_status()
        body = response.content
    feed = feedparser.parse(body)
    docs: list[dict[str, Any]] = []
    for entry in feed.entries:
        published_at = _parse_pub_date(entry)
        if since is not None and published_at < since:
            continue
        link = entry.get("link") or url_or_handle
        external_id = entry.get("id") or entry.get("guid") or link
        text = _entry_text(entry)
        title = (entry.get("title") or "").strip()
        if title and not text.startswith(title):
            text = f"{title}\n\n{text}".strip()
        if not text:
            continue
        author_field = entry.get("author") or feed.feed.get("title") or _channel_site_from_link(link)
        docs.append(
            {
                "source_id": str(source_id),
                "channel_kind": "rss",
                "channel_site": _channel_site_from_link(link),
                "external_id": f"rss:{external_id}",
                "url": link,
                "author": {"name": author_field, "handle": _channel_site_from_link(link)},
                "published_at": published_at,
                "fetched_at": _now(),
                "text": text,
                "lang": entry.get("language") or feed.feed.get("language"),
                "media": [],
                "raw_meta": {"feed_title": feed.feed.get("title")},
            }
        )
    logger.info("rss: source=%s — fetched %d entries", source_id, len(docs))
    return docs


__all__ = ["parse_source"]
