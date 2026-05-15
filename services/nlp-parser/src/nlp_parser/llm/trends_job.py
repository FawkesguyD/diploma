from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from nlp_parser.config import get_settings
from nlp_parser.llm.anthropic_client import extract_trends
from nlp_parser.persistence.mongo import TrendsRepo

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def recompute_trends(db: AsyncIOMotorDatabase) -> dict[str, Any] | None:
    settings = get_settings()
    period_end = _utcnow()
    period_start = period_end - timedelta(hours=settings.trends_window_hours)

    annotated_col = db["annotated_messages"]
    messages_col = db["messages"]

    pipeline = [
        {"$match": {"published_at": {"$gte": period_start}}},
        {"$sort": {"published_at": -1}},
        {"$limit": 500},
        {
            "$lookup": {
                "from": "annotated_messages",
                "localField": "_id",
                "foreignField": "message_id",
                "as": "ann",
            }
        },
        {
            "$addFields": {
                "annotation": {
                    "$first": {
                        "$filter": {
                            "input": "$ann",
                            "as": "a",
                            "cond": {"$eq": ["$$a.is_active", True]},
                        }
                    }
                }
            }
        },
        {
            "$match": {
                "$or": [
                    {"annotation": None},
                    {"annotation.is_ad": {"$ne": True}},
                ]
            }
        },
    ]

    docs: list[dict[str, Any]] = []
    async for doc in messages_col.aggregate(pipeline):
        docs.append(doc)

    if len(docs) < settings.trends_min_messages:
        logger.info(
            "recompute_trends: only %d messages in window (min %d) — skip",
            len(docs),
            settings.trends_min_messages,
        )
        _ = annotated_col
        return None

    compact: list[dict[str, Any]] = []
    for d in docs:
        text = d.get("text") or d.get("content") or ""
        ann = d.get("annotation") or {}
        topics = [t.get("slug") for t in ann.get("topics", []) if t.get("slug")]
        compact.append(
            {
                "id": str(d["_id"]),
                "text": text[:300],
                "topics": topics,
                "published_at": d.get("published_at"),
            }
        )

    trends = await extract_trends(compact, top_n=10)

    repo = TrendsRepo(db)
    prev = await repo.latest()
    prev_mentions: dict[str, int] = {}
    if prev:
        for t in prev.get("trends", []):
            slug = t.get("slug")
            if slug:
                prev_mentions[slug] = int(t.get("mentions", 0))

    snapshot = {
        "computed_at": _utcnow(),
        "window_hours": settings.trends_window_hours,
        "period_start": period_start,
        "period_end": period_end,
        "trends": trends,
        "prev_mentions": prev_mentions,
    }
    inserted_id = await repo.insert(snapshot)
    snapshot["_id"] = inserted_id
    return snapshot


__all__ = ["recompute_trends"]
