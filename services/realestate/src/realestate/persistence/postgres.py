"""Postgres-доступ: `core.model_registry` и `ops.model_runs`.

Используем SQLAlchemy Core (без ORM) — мы только читаем активную модель и
ведём журнал запусков; полная схема живёт в `model/alembic`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from realestate.config import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresClient:
    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_async_engine(settings.postgres_dsn, pool_pre_ping=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def session(self) -> AsyncSession:
        return self._sessionmaker()

    async def close(self) -> None:
        await self._engine.dispose()


class ModelRegistryRepo:
    """Чтение `core.model_registry`."""

    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def get_active(self, task: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, task, version, minio_path, metadata, is_active, created_at
            FROM core.model_registry
            WHERE task = :task AND is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"task": task})).mappings().first()
        return dict(row) if row else None

    async def get_by_version(self, task: str, version: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, task, version, minio_path, metadata, is_active, created_at
            FROM core.model_registry
            WHERE task = :task AND version = :version
            LIMIT 1
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"task": task, "version": version})).mappings().first()
        return dict(row) if row else None


class ModelRunsRepo:
    """Журнал `ops.model_runs`."""

    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        module: str,
        model_id: UUID,
        triggered_by: str = "queue",
        module_config_id: UUID | None = None,
    ) -> UUID:
        run_id = uuid4()
        sql = text(
            """
            INSERT INTO ops.model_runs
                (id, module, model_id, module_config_id, triggered_by, status,
                 started_at, items_processed, result_ref)
            VALUES
                (:id, :module, :model_id, :module_config_id, :triggered_by, 'running',
                 :started_at, 0, '{}'::jsonb)
            """
        )
        async with self._client.session() as session:
            await session.execute(
                sql,
                {
                    "id": run_id,
                    "module": module,
                    "model_id": model_id,
                    "module_config_id": module_config_id,
                    "triggered_by": triggered_by,
                    "started_at": _utcnow(),
                },
            )
            await session.commit()
        return run_id

    async def increment_processed(self, run_id: UUID, *, delta: int = 1) -> None:
        sql = text(
            "UPDATE ops.model_runs SET items_processed = items_processed + :delta WHERE id = :id"
        )
        async with self._client.session() as session:
            await session.execute(sql, {"id": run_id, "delta": delta})
            await session.commit()

    async def finish(
        self,
        run_id: UUID,
        *,
        status: str = "succeeded",
        error: str | None = None,
        result_ref: dict[str, Any] | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE ops.model_runs
            SET status = :status, finished_at = :finished_at, error = :error,
                result_ref = COALESCE(CAST(:result_ref AS jsonb), result_ref)
            WHERE id = :id
            """
        )
        async with self._client.session() as session:
            await session.execute(
                sql,
                {
                    "id": run_id,
                    "status": status,
                    "finished_at": _utcnow(),
                    "error": error,
                    "result_ref": None if result_ref is None else __import__("json").dumps(result_ref),
                },
            )
            await session.commit()

    async def list(
        self,
        *,
        module: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if module:
            clauses.append("module = :module")
            params["module"] = module
        if status:
            clauses.append("status = :status")
            params["status"] = status
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = text(
            f"""
            SELECT id, module, model_id, triggered_by, status,
                   started_at, finished_at, items_processed, error, result_ref
            FROM ops.model_runs
            {where}
            ORDER BY started_at DESC
            LIMIT :limit
            """
        )
        async with self._client.session() as session:
            rows = (await session.execute(sql, params)).mappings().all()
        return [dict(r) for r in rows]

    async def get(self, run_id: UUID) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, module, model_id, triggered_by, status,
                   started_at, finished_at, items_processed, error, result_ref
            FROM ops.model_runs WHERE id = :id
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": run_id})).mappings().first()
        return dict(row) if row else None


__all__ = ["PostgresClient", "ModelRegistryRepo", "ModelRunsRepo"]
