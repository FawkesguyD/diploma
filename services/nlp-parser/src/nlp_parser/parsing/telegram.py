from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.message import Message

from nlp_parser.config import Settings

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_handle(url_or_handle: str) -> str:
    handle = url_or_handle.strip()
    if handle.startswith("https://t.me/"):
        handle = handle[len("https://t.me/"):]
    elif handle.startswith("http://t.me/"):
        handle = handle[len("http://t.me/"):]
    elif handle.startswith("t.me/"):
        handle = handle[len("t.me/"):]
    handle = handle.strip("/").lstrip("@")
    if handle.startswith("s/"):
        handle = handle[2:]
    return handle


def is_configured(settings: Settings) -> bool:
    return bool(settings.tg_api_id and settings.tg_api_hash and settings.tg_session)


def _to_doc(
    *,
    source_id: UUID,
    handle: str,
    message: Message,
) -> dict[str, Any] | None:
    text = (message.message or "").strip()
    if not text:
        return None
    sender = message.sender
    author_name = getattr(sender, "title", None) or getattr(sender, "first_name", None) or handle
    author_handle = "@" + handle
    published_at = message.date or _now()
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    raw_meta: dict[str, Any] = {
        "views": getattr(message, "views", None) or 0,
        "forwards": getattr(message, "forwards", None) or 0,
        "reply_to_msg_id": getattr(getattr(message, "reply_to", None), "reply_to_msg_id", None),
    }
    return {
        "source_id": str(source_id),
        "channel_kind": "tg",
        "channel_site": "t.me",
        "external_id": f"tg:{handle}:{message.id}",
        "url": f"https://t.me/{handle}/{message.id}",
        "author": {"name": author_name, "handle": author_handle},
        "published_at": published_at,
        "fetched_at": _now(),
        "text": text,
        "lang": None,
        "media": [],
        "raw_meta": raw_meta,
    }


async def parse_source(
    source_id: UUID,
    *,
    url_or_handle: str,
    settings: Settings,
    since: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not is_configured(settings):
        raise RuntimeError("Telethon credentials not configured")
    if settings.tg_api_id is None or settings.tg_api_hash is None or settings.tg_session is None:
        raise RuntimeError("Telethon credentials not configured")
    handle = _normalize_handle(url_or_handle)
    effective_limit = limit if limit is not None else settings.tg_parse_limit
    client = TelegramClient(StringSession(settings.tg_session), settings.tg_api_id, settings.tg_api_hash)
    docs: list[dict[str, Any]] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telethon session not authorized — re-run tg_login script")
        async for message in client.iter_messages(handle, limit=effective_limit):
            if since is not None:
                msg_date = message.date
                if msg_date is not None and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)
                if msg_date is not None and msg_date < since:
                    break
            doc = _to_doc(source_id=source_id, handle=handle, message=message)
            if doc is not None:
                docs.append(doc)
    finally:
        await client.disconnect()
    logger.info("telegram: source=%s handle=%s — fetched %d", source_id, handle, len(docs))
    return docs


__all__ = ["parse_source", "is_configured"]
