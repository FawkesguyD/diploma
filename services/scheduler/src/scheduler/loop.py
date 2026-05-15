from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .config import Settings
from .db import SourcesRepo
from .publisher import ParserPublisher

logger = logging.getLogger(__name__)


class SchedulerLoop:
    def __init__(
        self,
        settings: Settings,
        repo: SourcesRepo,
        publisher: ParserPublisher,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._publisher = publisher
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_tick_at: datetime | None = None
        self._last_dispatched: int = 0
        self._total_dispatched: int = 0
        self._total_errors: int = 0

    @property
    def status(self) -> dict[str, object]:
        return {
            "running": self._task is not None and not self._task.done(),
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_dispatched": self._last_dispatched,
            "total_dispatched": self._total_dispatched,
            "total_errors": self._total_errors,
            "tick_interval_sec": self._settings.tick_interval_sec,
        }

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="scheduler-loop")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        logger.info("scheduler.loop.started", extra={"tick": self._settings.tick_interval_sec})
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                self._total_errors += 1
                logger.exception("scheduler.tick.failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._settings.tick_interval_sec
                )
            except asyncio.TimeoutError:
                continue
        logger.info("scheduler.loop.stopped")

    async def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        due = await self._repo.claim_due(limit=self._settings.batch_limit, now=now)
        self._last_tick_at = now
        self._last_dispatched = 0
        if not due:
            return
        for src in due:
            try:
                if src.kind == "realestate":
                    job_id = None
                else:
                    job_id = await self._repo.create_job(source_id=src.id, now=now)
                await self._publisher.publish_parse(
                    kind=src.kind, source_id=src.id, job_id=job_id
                )
                self._last_dispatched += 1
                self._total_dispatched += 1
                logger.info(
                    "scheduler.dispatched",
                    extra={"source_id": str(src.id), "kind": src.kind, "job_id": str(job_id)},
                )
            except Exception:
                self._total_errors += 1
                logger.exception(
                    "scheduler.dispatch.failed",
                    extra={"source_id": str(src.id), "kind": src.kind},
                )
