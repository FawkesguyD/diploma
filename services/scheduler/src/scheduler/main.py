from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from aisi_obs import configure_logging, configure_tracing, instrument_app

from .config import get_settings
from .db import SourcesRepo
from .loop import SchedulerLoop
from .publisher import ParserPublisher

configure_logging("scheduler")
configure_tracing("scheduler")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    repo = SourcesRepo(settings.database_url)
    publisher = ParserPublisher(settings)
    await publisher.connect()
    loop = SchedulerLoop(settings=settings, repo=repo, publisher=publisher)
    loop.start()
    app.state.settings = settings
    app.state.loop = loop
    try:
        yield
    finally:
        await loop.stop()
        await publisher.close()
        await repo.dispose()


app = FastAPI(title="scheduler", lifespan=lifespan)
instrument_app(app, "scheduler")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, object]:
    loop: SchedulerLoop = app.state.loop
    return loop.status
