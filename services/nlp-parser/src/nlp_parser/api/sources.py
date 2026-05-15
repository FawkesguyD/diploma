from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import aio_pika
import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from aisi_contracts.envelope import Envelope
from aisi_contracts.messages import ParseNewsCommand, ParseTelegramCommand

from nlp_parser.auth.jwt_tools import current_user, require_role
from nlp_parser.persistence.postgres import ParserJobsRepo, SourcesRepo

router = APIRouter(prefix="/api/sources", tags=["sources"])


_VALID_KINDS = {"tg", "news", "rss", "html", "realestate_site"}


class SourceCreate(BaseModel):
    kind: str = Field(..., description="tg | news | rss | html | realestate_site")
    name: str = Field(..., min_length=1, max_length=200)
    url_or_handle: str = Field(..., min_length=1, max_length=500)
    poll_interval_sec: int = Field(default=300, ge=10, le=86_400)
    config: dict[str, Any] = Field(default_factory=dict)


class SourcePatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    poll_interval_sec: int | None = Field(default=None, ge=10, le=86_400)
    config: dict[str, Any] | None = None


def _sources_repo(request: Request) -> SourcesRepo:
    return SourcesRepo(request.app.state.postgres)


def _jobs_repo(request: Request) -> ParserJobsRepo:
    return ParserJobsRepo(request.app.state.postgres)


def _source_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "name": row["name"],
        "url_or_handle": row["url_or_handle"],
        "enabled": row["enabled"],
        "poll_interval_sec": row["poll_interval_sec"],
        "config": row.get("config") or {},
        "last_polled_at": row.get("last_polled_at"),
    }


@router.get("")
async def list_sources(
    kind: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    sources: SourcesRepo = Depends(_sources_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    rows = await sources.list(kind=kind, enabled=enabled)
    return [_source_to_dict(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    sources: SourcesRepo = Depends(_sources_repo),
    _admin: dict[str, Any] = Depends(require_role("admin")),
):
    if body.kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind '{body.kind}'")
    row = await sources.create(
        kind=body.kind,
        name=body.name,
        url_or_handle=body.url_or_handle,
        poll_interval_sec=body.poll_interval_sec,
        config=body.config,
    )
    return _source_to_dict(row)


@router.patch("/{source_id}")
async def patch_source(
    source_id: UUID,
    body: SourcePatch,
    sources: SourcesRepo = Depends(_sources_repo),
    _admin: dict[str, Any] = Depends(require_role("admin")),
):
    row = await sources.patch(
        source_id,
        name=body.name,
        enabled=body.enabled,
        poll_interval_sec=body.poll_interval_sec,
        config=body.config,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="source not found")
    return _source_to_dict(row)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    sources: SourcesRepo = Depends(_sources_repo),
    _admin: dict[str, Any] = Depends(require_role("admin")),
):
    ok = await sources.soft_delete(source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="source not found")


@router.post("/{source_id}/parse", status_code=status.HTTP_202_ACCEPTED)
async def parse_now(
    source_id: UUID,
    request: Request,
    sources: SourcesRepo = Depends(_sources_repo),
    jobs: ParserJobsRepo = Depends(_jobs_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    source = await sources.get(source_id)
    if source is None or source.get("deleted_at") is not None:
        raise HTTPException(status_code=404, detail="source not found")
    kind = source["kind"]
    if kind not in {"tg", "news", "rss", "html"}:
        raise HTTPException(status_code=400, detail=f"kind '{kind}' is not parseable via nlp-parser")
    job_id = await jobs.create(source_id=source_id, status="pending")

    rabbit = getattr(request.app.state, "rabbit", None)
    if rabbit is None:
        await jobs.finish(job_id, status="failed", error="rabbitmq unavailable")
        raise HTTPException(status_code=503, detail="rabbitmq unavailable")
    settings = request.app.state.settings
    channel = await rabbit.channel()
    try:
        exchange = await channel.get_exchange(settings.exchange_parser, ensure=False)
        if kind == "tg":
            tg_envelope = Envelope[ParseTelegramCommand](
                payload=ParseTelegramCommand(
                    source_id=source_id, triggered_by="manual", job_id=job_id
                ),
                correlation_id=uuid4(),
            )
            routing_key = settings.routing_key_parse_tg
            body = orjson.dumps(tg_envelope.model_dump(mode="json"))
            message_id_str = str(tg_envelope.message_id)
            correlation_id_str = str(tg_envelope.correlation_id)
        else:
            news_envelope = Envelope[ParseNewsCommand](
                payload=ParseNewsCommand(
                    source_id=source_id, triggered_by="manual", job_id=job_id
                ),
                correlation_id=uuid4(),
            )
            routing_key = settings.routing_key_parse_news
            body = orjson.dumps(news_envelope.model_dump(mode="json"))
            message_id_str = str(news_envelope.message_id)
            correlation_id_str = str(news_envelope.correlation_id)
        msg = aio_pika.Message(
            body=body,
            content_type="application/json",
            message_id=message_id_str,
            correlation_id=correlation_id_str,
        )
        await exchange.publish(msg, routing_key=routing_key)
    finally:
        await channel.close()

    return {"job_id": str(job_id), "status_url": f"/api/jobs/{job_id}"}


__all__ = ["router"]
