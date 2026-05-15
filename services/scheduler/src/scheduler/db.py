from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DueSource:
    id: UUID
    kind: str
    name: str


class SourcesRepo:
    def __init__(self, dsn: str) -> None:
        self._engine: AsyncEngine = create_async_engine(dsn, pool_pre_ping=True)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def claim_due(self, *, limit: int, now: datetime) -> list[DueSource]:
        """
        Atomically pick due sources (enabled, not deleted, last_polled_at older
        than poll_interval_sec OR null), bump last_polled_at to NOW so a
        concurrent scheduler tick will not re-pick them.
        """
        sql = text(
            """
            WITH due AS (
                SELECT id
                FROM core.sources
                WHERE enabled = true
                  AND deleted_at IS NULL
                  AND kind IN ('tg', 'news', 'rss', 'html', 'realestate')
                  AND (
                        last_polled_at IS NULL
                        OR last_polled_at + (poll_interval_sec || ' seconds')::interval <= :now
                  )
                ORDER BY last_polled_at NULLS FIRST
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE core.sources s
               SET last_polled_at = :now,
                   updated_at     = :now
              FROM due
             WHERE s.id = due.id
            RETURNING s.id, s.kind, s.name
            """
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, {"now": now, "limit": limit})
            rows = result.all()
        return [DueSource(id=row.id, kind=row.kind, name=row.name) for row in rows]

    async def create_job(self, *, source_id: UUID, now: datetime) -> UUID:
        sql = text(
            """
            INSERT INTO ops.parser_jobs (source_id, status, started_at, metadata)
            VALUES (:source_id, 'pending', :now, '{"triggered_by":"scheduler"}'::jsonb)
            RETURNING id
            """
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(sql, {"source_id": source_id, "now": now})
            job_id: UUID = result.scalar_one()
        return job_id
