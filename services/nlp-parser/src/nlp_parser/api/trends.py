from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from nlp_parser.auth.jwt_tools import current_user
from nlp_parser.llm.trends_job import recompute_trends
from nlp_parser.nlp.content_filter import ContentFilter
from nlp_parser.persistence.mongo import TrendsRepo
from nlp_parser.persistence.postgres import ForbiddenKeywordsRepo

router = APIRouter(prefix="/api/trends", tags=["trends"])


def _repo(request: Request) -> TrendsRepo:
    return TrendsRepo(request.app.state.mongo.db)


def _content_filter(request: Request) -> ContentFilter:
    cf = getattr(request.app.state, "content_filter", None)
    if cf is None:
        cf = ContentFilter(ForbiddenKeywordsRepo(request.app.state.postgres))
        request.app.state.content_filter = cf
    return cf


def _delta_pct(curr: int, prev: int | None) -> float | None:
    if prev is None:
        return None
    if prev == 0:
        return None if curr == 0 else 100.0
    return round((curr - prev) / prev * 100.0, 2)


async def _serialize(doc: dict[str, Any], cf: ContentFilter) -> dict[str, Any]:
    prev_mentions = doc.get("prev_mentions") or {}
    items: list[dict[str, Any]] = []
    for t in doc.get("trends", []):
        slug = t.get("slug")
        blob = " ".join(
            str(v) for v in (t.get("title"), t.get("summary"), slug) if v
        )
        verdict = await cf.check(blob)
        if verdict.is_unwanted:
            continue
        mentions = int(t.get("mentions", 0))
        prev = prev_mentions.get(slug) if slug else None
        items.append(
            {
                "slug": slug,
                "title": t.get("title"),
                "mentions": mentions,
                "delta_pct": _delta_pct(mentions, prev),
                "summary": t.get("summary"),
                "sample_ids": t.get("sample_ids", []),
            }
        )
    return {
        "computed_at": doc.get("computed_at"),
        "period_start": doc.get("period_start"),
        "period_end": doc.get("period_end"),
        "items": items,
    }


@router.get("/latest")
async def latest_trends(
    request: Request,
    repo: TrendsRepo = Depends(_repo),
    _user: dict[str, Any] = Depends(current_user),
):
    doc = await repo.latest()
    if doc is None:
        raise HTTPException(status_code=404, detail="no trends snapshots yet")
    return await _serialize(doc, _content_filter(request))


@router.post("/recompute")
async def recompute(
    request: Request,
    _user: dict[str, Any] = Depends(current_user),
):
    snapshot = await recompute_trends(request.app.state.mongo.db)
    if snapshot is None:
        raise HTTPException(
            status_code=409, detail="not enough messages in window for recompute"
        )
    return await _serialize(snapshot, _content_filter(request))


__all__ = ["router"]


__all__ = ["router"]
