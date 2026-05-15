from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from nlp_parser.auth.jwt_tools import current_user
from nlp_parser.persistence.postgres import FavoritesRepo

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


_VALID_TARGET_KINDS = {"message", "object"}


class FavoriteBody(BaseModel):
    target_kind: str = Field(..., description="message | object")
    target_ref: str = Field(..., min_length=1, max_length=200)


def _repo(request: Request) -> FavoritesRepo:
    return FavoritesRepo(request.app.state.postgres)


def _to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "target_kind": row["target_kind"],
        "target_ref": row["target_ref"],
        "created_at": row["created_at"],
    }


@router.get("")
async def list_favorites(
    target_kind: str | None = Query(default=None),
    repo: FavoritesRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    if target_kind is not None and target_kind not in _VALID_TARGET_KINDS:
        raise HTTPException(status_code=400, detail=f"bad target_kind '{target_kind}'")
    rows = await repo.list_for_user(UUID(str(user["id"])), target_kind=target_kind)
    return [_to_dict(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    body: FavoriteBody,
    repo: FavoritesRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    if body.target_kind not in _VALID_TARGET_KINDS:
        raise HTTPException(status_code=400, detail=f"bad target_kind '{body.target_kind}'")
    row = await repo.add(
        user_id=UUID(str(user["id"])),
        target_kind=body.target_kind,
        target_ref=body.target_ref,
    )
    return _to_dict(row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(
    body: FavoriteBody,
    repo: FavoritesRepo = Depends(_repo),
    user: dict[str, Any] = Depends(current_user),
):
    if body.target_kind not in _VALID_TARGET_KINDS:
        raise HTTPException(status_code=400, detail=f"bad target_kind '{body.target_kind}'")
    await repo.remove(
        user_id=UUID(str(user["id"])),
        target_kind=body.target_kind,
        target_ref=body.target_ref,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
