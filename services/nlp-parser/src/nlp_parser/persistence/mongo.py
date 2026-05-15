from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from nlp_parser.config import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MongoClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncIOMotorClient(settings.mongo_url)
        self._db: AsyncIOMotorDatabase = self._client[settings.mongo_db]

    @property
    def db(self) -> AsyncIOMotorDatabase:
        return self._db

    async def close(self) -> None:
        self._client.close()


class MessagesRepo:
    COLLECTION = "messages"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[self.COLLECTION]

    async def get(self, message_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": ObjectId(message_id)})

    async def upsert_by_external_id(self, doc: dict[str, Any]) -> str:
        now = _utcnow()
        source_id = doc.get("source_id")
        external_id = doc.get("external_id")
        if source_id is None or external_id is None:
            raise ValueError("upsert_by_external_id требует source_id и external_id")
        set_on_insert = {"created_at": now}
        update_fields = {k: v for k, v in doc.items() if k not in set_on_insert}
        update_fields["updated_at"] = now
        result = await self._col.find_one_and_update(
            {"source_id": source_id, "external_id": external_id},
            {"$set": update_fields, "$setOnInsert": set_on_insert},
            upsert=True,
            return_document=True,
            projection={"_id": 1},
        )
        return str(result["_id"])

    async def find(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._col.find(filters or {})
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.limit(limit)
        return [doc async for doc in cursor]


class AnnotatedMessagesRepo:
    COLLECTION = "annotated_messages"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[self.COLLECTION]

    async def get_active(self, message_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(
            {"message_id": ObjectId(message_id), "is_active": True}
        )

    async def get_active_many(
        self, message_ids: Iterable[str]
    ) -> dict[str, dict[str, Any]]:
        oids = [ObjectId(x) for x in message_ids]
        cursor = self._col.find({"message_id": {"$in": oids}, "is_active": True})
        result: dict[str, dict[str, Any]] = {}
        async for doc in cursor:
            result[str(doc["message_id"])] = doc
        return result

    async def upsert_version(
        self,
        *,
        message_id: str,
        model_run_id: str,
        models: dict[str, str],
        is_ad: bool,
        ad_score: float,
        topics: list[dict[str, Any]],
        sentiment_label: str,
        sentiment_score: float,
        entities: list[dict[str, Any]],
        lang: str,
        summary: str | None = None,
    ) -> str:
        oid = ObjectId(message_id)
        now = _utcnow()
        await self._col.update_many(
            {"message_id": oid, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now}},
        )
        doc = {
            "message_id": oid,
            "model_run_id": model_run_id,
            "models": models,
            "is_ad": is_ad,
            "ad_score": ad_score,
            "topics": topics,
            "sentiment": {"label": sentiment_label, "score": sentiment_score},
            "entities": entities,
            "lang": lang,
            "summary": summary,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)


__all__ = ["MongoClient", "MessagesRepo", "AnnotatedMessagesRepo"]
