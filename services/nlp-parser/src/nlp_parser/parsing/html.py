from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
import trafilatura
from bs4 import BeautifulSoup

from nlp_parser.config import Settings

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _channel_site(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or "unknown"


def _extract_metadata(
    html: str, url: str
) -> tuple[str, datetime | None, str | None, str | None]:
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        with_metadata=True,
        output_format="json",
    )
    if not extracted:
        return "", None, None, None
    import json

    data = json.loads(extracted)
    text = (data.get("text") or "").strip()
    title = data.get("title") or None
    author = data.get("author") or None
    date_str = data.get("date") or None
    published_at: datetime | None = None
    if date_str:
        try:
            published_at = datetime.fromisoformat(date_str)
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = None
    return text, published_at, title, author


def _discover_links(html: str, base_url: str, link_selector: str | None) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    if link_selector:
        anchors = soup.select(link_selector)
    else:
        anchors = soup.select("a[href]")
    links: list[str] = []
    seen: set[str] = set()
    base_host = urlparse(base_url).netloc
    for anchor in anchors:
        href = anchor.get("href")
        if not href or not isinstance(href, str):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc and base_host and parsed.netloc != base_host:
            continue
        if absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("html: fetch failed url=%s err=%s", url, exc)
        return None
    return response.text


async def parse_source(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    config: dict[str, Any] | None = None,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    cfg = config or {}
    mode = cfg.get("mode", "single")
    link_selector = cfg.get("link_selector")
    max_articles = int(cfg.get("max_articles", 10))

    headers = {"User-Agent": settings.http_user_agent}
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_sec, headers=headers, follow_redirects=True
    ) as client:
        if mode == "single":
            urls = [url_or_handle]
        else:
            index_html = await _fetch(client, url_or_handle)
            if not index_html:
                return []
            urls = _discover_links(index_html, url_or_handle, link_selector)[:max_articles]

        docs: list[dict[str, Any]] = []
        for article_url in urls:
            html = await _fetch(client, article_url)
            if not html:
                continue
            text, published_at, title, author = _extract_metadata(html, article_url)
            if not text:
                continue
            published_at = published_at or _now()
            if since is not None and published_at < since:
                continue
            full_text = f"{title}\n\n{text}".strip() if title else text
            uid = hashlib.sha256(article_url.encode("utf-8")).hexdigest()[:16]
            site = _channel_site(article_url)
            docs.append(
                {
                    "source_id": str(source_id),
                    "channel_kind": "html",
                    "channel_site": site,
                    "external_id": f"html:{uid}",
                    "url": article_url,
                    "author": {"name": author or site, "handle": site},
                    "published_at": published_at,
                    "fetched_at": _now(),
                    "text": full_text,
                    "lang": None,
                    "media": [],
                    "raw_meta": {"title": title},
                }
            )
    logger.info("html: source=%s mode=%s — fetched %d", source_id, mode, len(docs))
    return docs


__all__ = ["parse_source"]
