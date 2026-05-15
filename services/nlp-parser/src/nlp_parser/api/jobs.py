from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from nlp_parser.auth.jwt_tools import current_user
from nlp_parser.persistence.postgres import ParserJobsRepo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _repo(request: Request) -> ParserJobsRepo:
    return ParserJobsRepo(request.app.state.postgres)


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    repo: ParserJobsRepo = Depends(_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    row = await repo.get(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": str(row["id"]),
        "kind": "parser",
        "status": row["status"],
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "progress": None,
        "result": {"items_collected": row.get("items_collected", 0)},
        "error": row.get("error"),
    }


__all__ = ["router"]
