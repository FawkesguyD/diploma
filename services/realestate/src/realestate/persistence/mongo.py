"""Motor-клиент Mongo + репозитории `objects` и `annotated_objects`."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from realestate.config import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MongoClient:
    """Тонкая обёртка над Motor — единый клиент на процесс."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncIOMotorClient(settings.mongo_url)
        self._db: AsyncIOMotorDatabase = self._client[settings.mongo_db]

    @property
    def db(self) -> AsyncIOMotorDatabase:
        return self._db

    async def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------

class ObjectsRepo:
    """Доступ к `objects` (сырые объявления)."""

    COLLECTION = "objects"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[self.COLLECTION]

    async def get(self, object_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": ObjectId(object_id)})

    async def get_many(self, object_ids: Iterable[str]) -> list[dict[str, Any]]:
        oids = [ObjectId(x) for x in object_ids]
        cursor = self._col.find({"_id": {"$in": oids}})
        return [doc async for doc in cursor]

    async def find(
        self,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        skip: int = 0,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._col.find(filters or {})
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        return [doc async for doc in cursor]

    async def history(self, object_id: str) -> list[dict[str, Any]]:
        doc = await self.get(object_id)
        if not doc:
            return []
        return doc.get("history", [])

    async def upsert_by_external_id(self, doc: dict[str, Any]) -> str:
        """Идемпотентный upsert по уникальному ключу (source_id, external_id).

        Возвращает hex-строку Mongo `_id` (либо обновлённого, либо вставленного документа).
        """
        now = _utcnow()
        source_id = doc.get("source_id")
        external_id = doc.get("external_id")
        if source_id is None or external_id is None:
            raise ValueError("upsert_by_external_id требует source_id и external_id")
        set_on_insert = {"created_at": now, "status": doc.get("status", "active")}
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

    async def iter_active(
        self,
        *,
        object_kind: str | None = None,
        city: str | None = None,
        district_slug: str | None = None,
    ):
        query: dict[str, Any] = {"status": "active"}
        if object_kind:
            query["object_kind"] = object_kind
        if city:
            query["listing.address.city"] = city
        if district_slug:
            query["listing.address.district_slug"] = district_slug
        async for doc in self._col.find(query):
            yield doc


class AnnotatedObjectsRepo:
    """Доступ к `annotated_objects` (результаты модели)."""

    COLLECTION = "annotated_objects"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[self.COLLECTION]

    async def get_active(self, object_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"object_id": ObjectId(object_id), "is_active": True})

    async def get_active_many(self, object_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        oids = [ObjectId(x) for x in object_ids]
        cursor = self._col.find({"object_id": {"$in": oids}, "is_active": True})
        result: dict[str, dict[str, Any]] = {}
        async for doc in cursor:
            result[str(doc["object_id"])] = doc
        return result

    async def top_undervalued(
        self,
        *,
        limit: int = 20,
        city: str | None = None,
        district_slug: str | None = None,
        object_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        match: dict[str, Any] = {"is_active": True, "is_undervalued": True}
        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {"$sort": {"deviation_pct": 1}},
            {"$limit": max(limit * 4, limit)},  # запас на пост-фильтрацию по объекту
            {
                "$lookup": {
                    "from": ObjectsRepo.COLLECTION,
                    "localField": "object_id",
                    "foreignField": "_id",
                    "as": "object",
                }
            },
            {"$unwind": "$object"},
        ]
        object_filter: dict[str, Any] = {}
        if city:
            object_filter["object.listing.address.city"] = city
        if district_slug:
            object_filter["object.listing.address.district_slug"] = district_slug
        if object_kind:
            object_filter["object.object_kind"] = object_kind
        if object_filter:
            pipeline.append({"$match": object_filter})
        pipeline.append({"$limit": limit})
        cursor = self._col.aggregate(pipeline)
        return [doc async for doc in cursor]

    async def upsert_version(
        self,
        *,
        object_id: str,
        model_run_id: str,
        model_version: str,
        predicted_price: float,
        deviation_abs: float | None,
        deviation_pct: float | None,
        is_undervalued: bool,
        features_used: dict[str, Any],
        rank_in_run: int | None = None,
    ) -> str:
        """Деактивирует старую активную аннотацию для object_id и вставляет новую."""
        oid = ObjectId(object_id)
        now = _utcnow()
        await self._col.update_many(
            {"object_id": oid, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now}},
        )
        doc = {
            "object_id": oid,
            "model_run_id": model_run_id,
            "model_version": model_version,
            "module": "realestate",
            "predicted_price": predicted_price,
            "deviation_abs": deviation_abs,
            "deviation_pct": deviation_pct,
            "is_undervalued": is_undervalued,
            "rank_in_run": rank_in_run,
            "features_used": features_used,
            "is_active": True,
            "computed_at": now,
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)

    async def update_rank(self, object_id: str, model_run_id: str, rank: int) -> None:
        await self._col.update_one(
            {"object_id": ObjectId(object_id), "model_run_id": model_run_id, "is_active": True},
            {"$set": {"rank_in_run": rank, "updated_at": _utcnow()}},
        )

    async def iter_by_run(self, model_run_id: str):
        async for doc in self._col.find({"model_run_id": model_run_id, "is_active": True}):
            yield doc


__all__ = ["MongoClient", "ObjectsRepo", "AnnotatedObjectsRepo"]
