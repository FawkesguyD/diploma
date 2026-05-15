from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from nlp_parser.auth.jwt_tools import current_user
from nlp_parser.persistence.postgres import SubscriptionsRepo

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


_VALID_TARGET_KINDS = {"source", "topic", "object"}


class SubscriptionCreate(BaseModel):
    target_kind: str = Field(..., description="source | topic | object")
    target_ref: str = Field(..., min_length=1, max_length=200)
    notify: bool = False


def _repo(request: Request) -> SubscriptionsRepo:
    return SubscriptionsRepo(request.app.state.postgres)


def _to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "target_kind": row["target_kind"],
        "target_ref": row["target_ref"],
        "notify": row["notify"],
        "created_at": row["created_at"],
    }


@router.get("")
async def list_subscriptions(
    repo: SubscriptionsRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    rows = await repo.list_for_user(UUID(str(user["id"])))
    return [_to_dict(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate,
    repo: SubscriptionsRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    if body.target_kind not in _VALID_TARGET_KINDS:
        raise HTTPException(status_code=400, detail=f"bad target_kind '{body.target_kind}'")
    row = await repo.create(
        user_id=UUID(str(user["id"])),
        target_kind=body.target_kind,
        target_ref=body.target_ref,
        notify=body.notify,
    )
    return _to_dict(row)


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    sub_id: UUID,
    repo: SubscriptionsRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    ok = await repo.delete(sub_id=sub_id, user_id=UUID(str(user["id"])))
    if not ok:
        raise HTTPException(status_code=404, detail="subscription not found")


__all__ = ["router"]
