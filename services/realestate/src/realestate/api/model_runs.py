"""`/api/model-runs/*` — журнал запусков моделей realestate."""
from __future__ import annotations

from uuid import UUID, uuid4

import aio_pika
import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from aisi_contracts.envelope import Envelope
from aisi_contracts.realestate import ScoreCommand

from realestate.persistence.postgres import ModelRunsRepo

router = APIRouter(prefix="/api/model-runs", tags=["model-runs"])


class TriggerRunBody(BaseModel):
    object_ids: list[str] = Field(..., min_length=1)
    model_version: str | None = None
    force: bool = False


def _runs_repo(request: Request) -> ModelRunsRepo:
    return ModelRunsRepo(request.app.state.postgres)


def _serialize(row: dict):
    out = dict(row)
    for k in ("id", "model_id"):
        if k in out and out[k] is not None:
            out[k] = str(out[k])
    return out


@router.get("")
async def list_runs(
    module: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    runs: ModelRunsRepo = Depends(_runs_repo),
):
    rows = await runs.list(module=module, status=status_, limit=limit)
    return {"items": [_serialize(r) for r in rows]}


@router.get("/{run_id}")
async def get_run(run_id: UUID, runs: ModelRunsRepo = Depends(_runs_repo)):
    row = await runs.get(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="model_run not found")
    return _serialize(row)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(body: TriggerRunBody, request: Request):
    """Публикует команду в `realestate.score` (admin-операция).

    Возвращает `{job_id}` сразу — фактическое выполнение асинхронное.
    """
    settings = request.app.state.settings
    connection: aio_pika.RobustConnection = request.app.state.rabbit
    channel = await connection.channel()
    try:
        exchange = await channel.get_exchange(settings.exchange_realestate, ensure=False)
        envelope = Envelope[ScoreCommand](
            payload=ScoreCommand(
                object_ids=body.object_ids, model_version=body.model_version, force=body.force
            )
        )
        msg = aio_pika.Message(
            body=orjson.dumps(envelope.model_dump(mode="json")),
            content_type="application/json",
            message_id=str(envelope.message_id),
            correlation_id=str(envelope.correlation_id),
        )
        await exchange.publish(msg, routing_key=settings.routing_key_score)
    finally:
        await channel.close()
    return {"job_id": str(uuid4()), "status": "accepted", "queued": settings.queue_score}
