from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

from nlp_parser.config import get_settings
from nlp_parser.nlp.content_filter import ContentFilter
from nlp_parser.persistence.mongo import MongoClient
from nlp_parser.persistence.postgres import ForbiddenKeywordsRepo, PostgresClient

logger = logging.getLogger("sanitize_trends")


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    settings = get_settings()
    mongo = MongoClient(settings)
    postgres = PostgresClient(settings)
    cf = ContentFilter(ForbiddenKeywordsRepo(postgres))
    col = mongo.db["trends"]
    now = datetime.now(timezone.utc)

    scanned = 0
    sanitized = 0
    removed_items = 0
    async for snap in col.find({}, projection={"_id": 1, "trends": 1}):
        scanned += 1
        trends = snap.get("trends") or []
        clean: list[dict] = []
        dropped = 0
        for t in trends:
            blob = " ".join(str(v) for v in (t.get("title"), t.get("summary"), t.get("slug")) if v)
            verdict = await cf.check(blob)
            if verdict.is_unwanted:
                dropped += 1
                continue
            clean.append(t)
        if dropped:
            await col.update_one(
                {"_id": snap["_id"]},
                {"$set": {"trends": clean, "sanitized_at": now}},
            )
            sanitized += 1
            removed_items += dropped

    logger.info(
        "sanitize_trends: scanned=%d sanitized_snapshots=%d removed_items=%d",
        scanned, sanitized, removed_items,
    )
    await postgres.close()
    await mongo.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
