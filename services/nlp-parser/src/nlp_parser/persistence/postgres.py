from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from nlp_parser.config import Settings


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


class UsersRepo:
    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, email, password_hash, display_name, role, is_active, created_at
            FROM core.users WHERE email = :email
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"email": email})).mappings().first()
        return dict(row) if row else None

    async def get_by_id(self, user_id: UUID) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, email, password_hash, display_name, role, is_active, created_at
            FROM core.users WHERE id = :id
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": user_id})).mappings().first()
        return dict(row) if row else None

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str | None = None,
        role: str = "user",
    ) -> dict[str, Any]:
        user_id = uuid4()
        sql = text(
            """
            INSERT INTO core.users (id, email, password_hash, display_name, role)
            VALUES (:id, :email, :password_hash, :display_name, :role)
            RETURNING id, email, password_hash, display_name, role, is_active, created_at
            """
        )
        async with self._client.session() as session:
            row = (
                await session.execute(
                    sql,
                    {
                        "id": user_id,
                        "email": email,
                        "password_hash": password_hash,
                        "display_name": display_name,
                        "role": role,
                    },
                )
            ).mappings().first()
            await session.commit()
        if row is None:
            raise RuntimeError("INSERT INTO core.users RETURNING вернул NULL")
        return dict(row)

    async def update_profile(
        self,
        user_id: UUID,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        params: dict[str, Any] = {"id": user_id}
        if email is not None:
            sets.append("email = :email")
            params["email"] = email
        if display_name is not None:
            sets.append("display_name = :display_name")
            params["display_name"] = display_name
        if not sets:
            return await self.get_by_id(user_id)
        sql = text(
            f"""
            UPDATE core.users SET {', '.join(sets)}
            WHERE id = :id
            RETURNING id, email, password_hash, display_name, role, is_active, created_at
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, params)).mappings().first()
            await session.commit()
        return dict(row) if row else None

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        sql = text("UPDATE core.users SET password_hash = :ph WHERE id = :id")
        async with self._client.session() as session:
            await session.execute(sql, {"id": user_id, "ph": password_hash})
            await session.commit()


class SourcesRepo:
    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def list(
        self, *, kind: str | None = None, enabled: bool | None = None
    ) -> list[dict[str, Any]]:
        clauses = ["deleted_at IS NULL"]
        params: dict[str, Any] = {}
        if kind is not None:
            clauses.append("kind = :kind")
            params["kind"] = kind
        if enabled is not None:
            clauses.append("enabled = :enabled")
            params["enabled"] = enabled
        sql = text(
            f"""
            SELECT id, kind, name, url_or_handle, enabled, poll_interval_sec,
                   config, last_polled_at, created_at, updated_at
            FROM core.sources
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            """
        )
        async with self._client.session() as session:
            rows = (await session.execute(sql, params)).mappings().all()
        return [dict(r) for r in rows]

    async def get(self, source_id: UUID) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, kind, name, url_or_handle, enabled, poll_interval_sec,
                   config, last_polled_at, created_at, updated_at, deleted_at
            FROM core.sources WHERE id = :id
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": source_id})).mappings().first()
        return dict(row) if row else None

    async def create(
        self,
        *,
        kind: str,
        name: str,
        url_or_handle: str,
        poll_interval_sec: int = 300,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_id = uuid4()
        sql = text(
            """
            INSERT INTO core.sources (id, kind, name, url_or_handle, poll_interval_sec, config)
            VALUES (:id, :kind, :name, :url_or_handle, :poll_interval_sec, CAST(:config AS jsonb))
            RETURNING id, kind, name, url_or_handle, enabled, poll_interval_sec,
                      config, last_polled_at, created_at, updated_at
            """
        )
        async with self._client.session() as session:
            row = (
                await session.execute(
                    sql,
                    {
                        "id": source_id,
                        "kind": kind,
                        "name": name,
                        "url_or_handle": url_or_handle,
                        "poll_interval_sec": poll_interval_sec,
                        "config": json.dumps(config or {}),
                    },
                )
            ).mappings().first()
            await session.commit()
        if row is None:
            raise RuntimeError("INSERT INTO core.sources RETURNING вернул NULL")
        return dict(row)

    async def patch(
        self,
        source_id: UUID,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        poll_interval_sec: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        params: dict[str, Any] = {"id": source_id}
        if name is not None:
            sets.append("name = :name")
            params["name"] = name
        if enabled is not None:
            sets.append("enabled = :enabled")
            params["enabled"] = enabled
        if poll_interval_sec is not None:
            sets.append("poll_interval_sec = :poll_interval_sec")
            params["poll_interval_sec"] = poll_interval_sec
        if config is not None:
            sets.append("config = CAST(:config AS jsonb)")
            params["config"] = json.dumps(config)
        if not sets:
            return await self.get(source_id)
        sets.append("updated_at = now()")
        sql = text(
            f"""
            UPDATE core.sources SET {', '.join(sets)}
            WHERE id = :id AND deleted_at IS NULL
            RETURNING id, kind, name, url_or_handle, enabled, poll_interval_sec,
                      config, last_polled_at, created_at, updated_at
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, params)).mappings().first()
            await session.commit()
        return dict(row) if row else None

    async def soft_delete(self, source_id: UUID) -> bool:
        sql = text(
            """
            UPDATE core.sources SET deleted_at = now()
            WHERE id = :id AND deleted_at IS NULL
            RETURNING id
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": source_id})).first()
            await session.commit()
        return row is not None

    async def mark_polled(self, source_id: UUID) -> None:
        sql = text(
            "UPDATE core.sources SET last_polled_at = :now WHERE id = :id"
        )
        async with self._client.session() as session:
            await session.execute(sql, {"id": source_id, "now": _utcnow()})
            await session.commit()


class SubscriptionsRepo:
    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def list_for_user(self, user_id: UUID) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT id, user_id, target_kind, target_id, target_ref, notify, created_at
            FROM core.user_subscriptions WHERE user_id = :user_id
            ORDER BY created_at DESC
            """
        )
        async with self._client.session() as session:
            rows = (await session.execute(sql, {"user_id": user_id})).mappings().all()
        return [dict(r) for r in rows]

    async def create(
        self,
        *,
        user_id: UUID,
        target_kind: str,
        target_ref: str,
        target_id: UUID | None = None,
        notify: bool = False,
    ) -> dict[str, Any]:
        sub_id = uuid4()
        sql = text(
            """
            INSERT INTO core.user_subscriptions
                (id, user_id, target_kind, target_id, target_ref, notify)
            VALUES
                (:id, :user_id, :target_kind, :target_id, :target_ref, :notify)
            RETURNING id, user_id, target_kind, target_id, target_ref, notify, created_at
            """
        )
        async with self._client.session() as session:
            row = (
                await session.execute(
                    sql,
                    {
                        "id": sub_id,
                        "user_id": user_id,
                        "target_kind": target_kind,
                        "target_id": target_id,
                        "target_ref": target_ref,
                        "notify": notify,
                    },
                )
            ).mappings().first()
            await session.commit()
        if row is None:
            raise RuntimeError("INSERT INTO core.user_subscriptions RETURNING вернул NULL")
        return dict(row)

    async def delete(self, *, sub_id: UUID, user_id: UUID) -> bool:
        sql = text(
            "DELETE FROM core.user_subscriptions WHERE id = :id AND user_id = :user_id RETURNING id"
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": sub_id, "user_id": user_id})).first()
            await session.commit()
        return row is not None


class ParserJobsRepo:
    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        source_id: UUID,
        status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        job_id = uuid4()
        sql = text(
            """
            INSERT INTO ops.parser_jobs (id, source_id, status, started_at, metadata)
            VALUES (:id, :source_id, :status, :started_at, CAST(:metadata AS jsonb))
            """
        )
        async with self._client.session() as session:
            await session.execute(
                sql,
                {
                    "id": job_id,
                    "source_id": source_id,
                    "status": status,
                    "started_at": _utcnow() if status == "running" else None,
                    "metadata": json.dumps(metadata or {}),
                },
            )
            await session.commit()
        return job_id

    async def get(self, job_id: UUID) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT id, source_id, status, started_at, finished_at,
                   items_collected, error, metadata
            FROM ops.parser_jobs WHERE id = :id
            """
        )
        async with self._client.session() as session:
            row = (await session.execute(sql, {"id": job_id})).mappings().first()
        return dict(row) if row else None

    async def finish(
        self,
        job_id: UUID,
        *,
        status: str,
        items_collected: int = 0,
        error: str | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE ops.parser_jobs
            SET status = :status,
                finished_at = :finished_at,
                items_collected = :items_collected,
                error = :error
            WHERE id = :id
            """
        )
        async with self._client.session() as session:
            await session.execute(
                sql,
                {
                    "id": job_id,
                    "status": status,
                    "finished_at": _utcnow(),
                    "items_collected": items_collected,
                    "error": error,
                },
            )
            await session.commit()


class FavoritesRepo:
    def __init__(self, client: PostgresClient) -> None:
        self._client = client

    async def list_for_user(
        self, user_id: UUID, target_kind: str | None = None
    ) -> list[dict[str, Any]]:
        clauses = ["user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}
        if target_kind is not None:
            clauses.append("target_kind = :target_kind")
            params["target_kind"] = target_kind
        sql = text(
            f"""
            SELECT id, user_id, target_kind, target_ref, created_at
            FROM core.favorites
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            """
        )
        async with self._client.session() as session:
            rows = (await session.execute(sql, params)).mappings().all()
        return [dict(r) for r in rows]

    async def add(
        self, *, user_id: UUID, target_kind: str, target_ref: str
    ) -> dict[str, Any]:
        fav_id = uuid4()
        sql = text(
            """
            INSERT INTO core.favorites (id, user_id, target_kind, target_ref)
            VALUES (:id, :user_id, :target_kind, :target_ref)
            ON CONFLICT (user_id, target_kind, target_ref) DO UPDATE
                SET target_ref = EXCLUDED.target_ref
            RETURNING id, user_id, target_kind, target_ref, created_at
            """
        )
        async with self._client.session() as session:
            row = (
                await session.execute(
                    sql,
                    {
                        "id": fav_id,
                        "user_id": user_id,
                        "target_kind": target_kind,
                        "target_ref": target_ref,
                    },
                )
            ).mappings().first()
            await session.commit()
        if row is None:
            raise RuntimeError("INSERT INTO core.favorites RETURNING вернул NULL")
        return dict(row)

    async def remove(
        self, *, user_id: UUID, target_kind: str, target_ref: str
    ) -> bool:
        sql = text(
            """
            DELETE FROM core.favorites
            WHERE user_id = :user_id AND target_kind = :target_kind AND target_ref = :target_ref
            RETURNING id
            """
        )
        async with self._client.session() as session:
            row = (
                await session.execute(
                    sql,
                    {
                        "user_id": user_id,
                        "target_kind": target_kind,
                        "target_ref": target_ref,
                    },
                )
            ).first()
            await session.commit()
        return row is not None


__all__ = [
    "PostgresClient",
    "UsersRepo",
    "SourcesRepo",
    "SubscriptionsRepo",
    "FavoritesRepo",
    "ParserJobsRepo",
]
