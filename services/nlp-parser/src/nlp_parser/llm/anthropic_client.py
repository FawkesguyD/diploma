from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from nlp_parser.config import get_settings

logger = logging.getLogger(__name__)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


async def extract_trends(messages: list[dict[str, Any]], *, top_n: int = 10) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.anthropic_auth_token:
        logger.warning("ANTHROPIC_AUTH_TOKEN не задан — trends extraction пропущен.")
        return []

    payload_messages = json.dumps(messages, ensure_ascii=False, default=str)
    system_prompt = (
        "Ты аналитик информационных потоков. Отвечай СТРОГО валидным JSON без какого-либо "
        "текста до или после, без markdown-обёрток. Используй только указанную схему."
    )
    user_prompt = (
        f"Дан список сообщений из новостных и Telegram-каналов. "
        f"Выдели топ-{top_n} главных трендов (сущность или тема) за период. "
        "Для каждого тренда укажи: slug (латиница, kebab-case), title (на русском), "
        "mentions (число упоминаний), summary (одна строка, на русском, без воды) и "
        "sample_ids (до 5 id из исходных сообщений).\n\n"
        'Ответ строго в формате: {"trends":[{"slug":"...","title":"...","mentions":N,'
        '"summary":"...","sample_ids":["..."]}]}\n\n'
        f"Сообщения (JSON):\n{payload_messages}"
    )

    body = {
        "model": settings.anthropic_model,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": settings.anthropic_auth_token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = f"{settings.anthropic_base_url.rstrip('/')}/messages"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Anthropic request failed")
        return []

    try:
        text_part = data["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        logger.error("Anthropic response missing content[0].text: %r", data)
        return []

    cleaned = _strip_fences(text_part)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.exception("Failed to parse Anthropic JSON: %r", cleaned[:500])
        return []

    trends = parsed.get("trends") if isinstance(parsed, dict) else None
    if not isinstance(trends, list):
        logger.error("Anthropic JSON has no 'trends' list: %r", parsed)
        return []
    return trends


__all__ = ["extract_trends"]
