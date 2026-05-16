from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

from nlp_parser.config import get_settings
from nlp_parser.nlp.content_filter import ContentFilter
from nlp_parser.persistence.mongo import MongoClient
from nlp_parser.persistence.postgres import ForbiddenKeywordsRepo, PostgresClient

logger = logging.getLogger("backfill_unwanted")


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    settings = get_settings()
    mongo = MongoClient(settings)
    postgres = PostgresClient(settings)
    cf = ContentFilter(ForbiddenKeywordsRepo(postgres))

    db = mongo.db
    messages = db["messages"]
    annotated = db["annotated_messages"]
    now = datetime.now(timezone.utc)

    cursor = messages.find({}, projection={"_id": 1, "text": 1})
    scanned = 0
    flagged = 0
    deleted_msgs = 0
    deleted_anno = 0
    async for doc in cursor:
        scanned += 1
        text = doc.get("text") or ""
        result = await cf.check(text)
        if not result.is_unwanted:
            continue
        flagged += 1
        oid = doc["_id"]
        await annotated.update_many(
            {"message_id": oid},
            {"$set": {
                "is_unwanted": True,
                "unwanted_reasons": result.reasons,
                "is_active": False,
                "updated_at": now,
            }},
        )
        del_anno = await annotated.delete_many({"message_id": oid})
        deleted_anno += del_anno.deleted_count
        del_msg = await messages.delete_one({"_id": oid})
        deleted_msgs += del_msg.deleted_count

    logger.info(
        "backfill: scanned=%d flagged=%d deleted_messages=%d deleted_annotations=%d",
        scanned, flagged, deleted_msgs, deleted_anno,
    )
    await postgres.close()
    await mongo.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
