from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from nlp_parser.auth.jwt_tools import current_user, current_user_sse
from nlp_parser.persistence.mongo import AnnotatedMessagesRepo, MessagesRepo

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _messages_repo(request: Request) -> MessagesRepo:
    return MessagesRepo(request.app.state.mongo.db)


def _annotated_repo(request: Request) -> AnnotatedMessagesRepo:
    return AnnotatedMessagesRepo(request.app.state.mongo.db)


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


def _message_to_dict(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    return out


def _annotation_to_dict(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    return {
        "is_ad": doc.get("is_ad", False),
        "ad_score": doc.get("ad_score", 0.0),
        "topics": doc.get("topics", []),
        "sentiment": doc.get("sentiment", {"label": "neutral", "score": 0.5}),
        "entities": doc.get("entities", []),
        "summary": doc.get("summary"),
        "lang": doc.get("lang", "ru"),
    }


@router.get("")
async def list_messages(
    topic: str | None = Query(default=None),
    district: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    channel_kind: str | None = Query(default=None),
    channel_site: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    is_ad: bool | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    messages: MessagesRepo = Depends(_messages_repo),
    annotated: AnnotatedMessagesRepo = Depends(_annotated_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    filters: dict[str, Any] = {}
    if channel_kind:
        filters["channel_kind"] = channel_kind
    if channel_site:
        filters["channel_site"] = channel_site
    if source_id:
        filters["source_id"] = source_id

    date_clause: dict[str, Any] = {}
    if since is not None:
        date_clause["$gte"] = since
    if until is not None:
        date_clause["$lte"] = until
    if date_clause:
        filters["published_at"] = date_clause

    if cursor is not None:
        try:
            cursor_oid = _decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filters["_id"] = {"$gt": cursor_oid}

    docs = await messages.find(filters=filters, limit=limit, sort=[("_id", 1)])
    annotations = await annotated.get_active_many([str(d["_id"]) for d in docs])

    items: list[dict[str, Any]] = []
    for doc in docs:
        item = _message_to_dict(doc)
        annotation_doc = annotations.get(item["id"])
        annotation = _annotation_to_dict(annotation_doc)

        if topic is not None:
            topic_slugs = {t.get("slug") for t in (annotation or {}).get("topics", [])}
            if topic not in topic_slugs:
                continue
        if district is not None:
            districts = {
                e.get("district_slug")
                for e in (annotation or {}).get("entities", [])
                if e.get("type") == "location"
            }
            if district not in districts:
                continue
        if sentiment is not None:
            if (annotation or {}).get("sentiment", {}).get("label") != sentiment:
                continue
        if is_ad is not None:
            if bool((annotation or {}).get("is_ad", False)) != is_ad:
                continue

        item["annotation"] = annotation
        items.append(item)

    next_cursor: str | None = None
    if len(docs) == limit and docs:
        next_cursor = _encode_cursor(docs[-1]["_id"])
    return {"items": items, "next_cursor": next_cursor}


@router.get("/stream")
async def stream_messages(
    request: Request,
    topic: str | None = Query(default=None),
    channel_kind: str | None = Query(default=None),
    _user: dict[str, Any] = Depends(current_user_sse),
):
    pubsub = request.app.state.pubsub

    async def event_generator():
        queue = await pubsub.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if channel_kind is not None and event.get("channel_kind") != channel_kind:
                    continue
                if topic is not None:
                    topic_slugs = {t.get("slug") for t in event.get("annotation", {}).get("topics", [])}
                    if topic not in topic_slugs:
                        continue
                yield {"event": "message", "data": json.dumps(event, default=str)}
        finally:
            await pubsub.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.get("/{message_id}")
async def get_message(
    message_id: str,
    messages: MessagesRepo = Depends(_messages_repo),
    annotated: AnnotatedMessagesRepo = Depends(_annotated_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    try:
        ObjectId(message_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail=f"bad message_id: {exc}") from exc
    doc = await messages.get(message_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="message not found")
    annotation = await annotated.get_active(message_id)
    payload = _message_to_dict(doc)
    payload["annotation"] = _annotation_to_dict(annotation)
    return payload


__all__ = ["router", "_encode_cursor", "_decode_cursor"]
