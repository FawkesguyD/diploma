"""`/api/objects/*` — объекты недвижимости + актуальные оценки."""
from __future__ import annotations

import base64
import binascii
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from realestate.persistence.mongo import AnnotatedObjectsRepo, ObjectsRepo

router = APIRouter(prefix="/api/objects", tags=["objects"])


_EVALUATION_FIELDS = (
    "model_version",
    "model_run_id",
    "predicted_price",
    "deviation_abs",
    "deviation_pct",
    "is_undervalued",
    "rank_in_run",
    "features_used",
    "computed_at",
    "is_active",
)


def _objects_repo(request: Request) -> ObjectsRepo:
    return ObjectsRepo(request.app.state.mongo.db)


def _annotated_repo(request: Request) -> AnnotatedObjectsRepo:
    return AnnotatedObjectsRepo(request.app.state.mongo.db)


def _object_to_dict(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    return out


def _evaluation_to_dict(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    out: dict[str, Any] = {}
    if "_id" in doc:
        out["id"] = str(doc["_id"])
    if "object_id" in doc:
        out["object_id"] = str(doc["object_id"])
    if "evaluated_at" in doc:
        out["evaluated_at"] = doc["evaluated_at"]
    for field in _EVALUATION_FIELDS:
        if field in doc:
            out[field] = doc[field]
    if "evaluated_at" not in out and "computed_at" in doc:
        out["evaluated_at"] = doc["computed_at"]
    return out


def _encode_cursor(object_id: ObjectId | str) -> str:
    hex_value = str(object_id) if isinstance(object_id, ObjectId) else object_id
    return base64.urlsafe_b64encode(hex_value.encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> ObjectId:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        hex_value = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("malformed cursor") from exc
    try:
        return ObjectId(hex_value)
    except InvalidId as exc:
        raise ValueError("malformed cursor") from exc


@router.get("/top-undervalued")
async def top_undervalued(
    limit: int = Query(default=20, ge=1, le=200),
    city: str | None = Query(default=None),
    district: str | None = Query(default=None, alias="district"),
    object_kind: str | None = Query(default=None),
    annotated: AnnotatedObjectsRepo = Depends(_annotated_repo),
):
    rows = await annotated.top_undervalued(
        limit=limit, city=city, district_slug=district, object_kind=object_kind
    )
    items = []
    for row in rows:
        obj = row.pop("object", None)
        evaluation = _evaluation_to_dict(row)
        item: dict[str, Any] = {"evaluation": evaluation}
        if obj is not None:
            item.update(_object_to_dict(obj))
        items.append(item)
    return {"items": items, "total": len(items)}


@router.get("")
async def list_objects(
    object_kind: str | None = Query(default=None),
    channel_site: str | None = Query(default=None),
    city: str | None = Query(default=None),
    district: str | None = Query(default=None),
    rooms: int | None = Query(default=None),
    price_min: float | None = Query(default=None, ge=0),
    price_max: float | None = Query(default=None, ge=0),
    is_undervalued: bool | None = Query(default=None),
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    objects: ObjectsRepo = Depends(_objects_repo),
    annotated: AnnotatedObjectsRepo = Depends(_annotated_repo),
):
    filters: dict[str, Any] = {}
    if object_kind:
        filters["object_kind"] = object_kind
    if channel_site:
        filters["channel_site"] = channel_site
    if city:
        filters["listing.address.city"] = city
    if district:
        filters["listing.address.district_slug"] = district
    if rooms is not None:
        filters["listing.rooms"] = rooms
    if status:
        filters["status"] = status
    price_clause: dict[str, Any] = {}
    if price_min is not None:
        price_clause["$gte"] = price_min
    if price_max is not None:
        price_clause["$lte"] = price_max
    if price_clause:
        filters["listing.price"] = price_clause

    if cursor is not None:
        try:
            cursor_oid = _decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filters["_id"] = {"$gt": cursor_oid}

    docs = await objects.find(
        filters=filters, limit=limit, skip=0, sort=[("_id", 1)]
    )
    annotations = await annotated.get_active_many([str(d["_id"]) for d in docs])

    items: list[dict[str, Any]] = []
    for doc in docs:
        item = _object_to_dict(doc)
        annotation = annotations.get(item["id"])
        if is_undervalued is not None:
            ann_under = bool(annotation and annotation.get("is_undervalued"))
            if ann_under != is_undervalued:
                continue
        item["evaluation"] = _evaluation_to_dict(annotation) if annotation else None
        items.append(item)

    next_cursor: str | None = None
    if len(docs) == limit and docs:
        next_cursor = _encode_cursor(docs[-1]["_id"])
    return {"items": items, "next_cursor": next_cursor}


@router.get("/{object_id}")
async def get_object(
    object_id: str,
    objects: ObjectsRepo = Depends(_objects_repo),
    annotated: AnnotatedObjectsRepo = Depends(_annotated_repo),
):
    try:
        ObjectId(object_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail=f"Bad object_id: {exc}") from exc
    doc = await objects.get(object_id)
    if not doc:
        raise HTTPException(status_code=404, detail="object not found")
    annotation = await annotated.get_active(object_id)
    payload = _object_to_dict(doc)
    payload["evaluation"] = _evaluation_to_dict(annotation)
    return payload


@router.get("/{object_id}/history")
async def object_history(object_id: str, objects: ObjectsRepo = Depends(_objects_repo)):
    try:
        ObjectId(object_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail=f"Bad object_id: {exc}") from exc
    history = await objects.history(object_id)
    if not history and not await objects.get(object_id):
        raise HTTPException(status_code=404, detail="object not found")
    return {"object_id": object_id, "history": history}


__all__ = ["router", "_encode_cursor", "_decode_cursor"]
