from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from nlp_parser.persistence.postgres import ForbiddenKeywordsRepo

logger = logging.getLogger(__name__)

_RELOAD_INTERVAL_SEC = 60.0


@dataclass
class FilterResult:
    is_unwanted: bool
    reasons: list[str]


class ContentFilter:
    def __init__(self, repo: ForbiddenKeywordsRepo) -> None:
        self._repo = repo
        self._keywords: tuple[str, ...] = ()
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._keywords and time.monotonic() - self._loaded_at < _RELOAD_INTERVAL_SEC:
            return
        async with self._lock:
            if self._keywords and time.monotonic() - self._loaded_at < _RELOAD_INTERVAL_SEC:
                return
            try:
                kws = await self._repo.list_active()
            except Exception:
                logger.exception("ContentFilter: не удалось загрузить core.forbidden_keywords")
                return
            self._keywords = tuple(k for k in kws if k)
            self._loaded_at = time.monotonic()
            logger.info("ContentFilter: загружено %d стопов", len(self._keywords))

    async def check(self, text: str) -> FilterResult:
        await self._ensure_loaded()
        if not text or not self._keywords:
            return FilterResult(is_unwanted=False, reasons=[])
        low = text.lower()
        hits = [kw for kw in self._keywords if kw in low]
        return FilterResult(is_unwanted=bool(hits), reasons=hits[:5])


__all__ = ["ContentFilter", "FilterResult"]
