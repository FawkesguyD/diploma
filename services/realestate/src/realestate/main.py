"""FastAPI-приложение realestate.

Lifecycle:
* startup — подключаемся к Postgres/Mongo/RabbitMQ/Kafka, тянем активную
  модель из MinIO, поднимаем worker;
* shutdown — корректно гасим всё в обратном порядке.

Если активной модели в `core.model_registry` ещё нет — сервис всё равно
поднимется (для smoke и фронт-эндпоинтов чтения), но worker не стартует и
эндпоинты scoring'а вернут 503 при попытке инференса.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

import aio_pika
from fastapi import FastAPI

from aisi_obs import configure_logging, configure_tracing, instrument_app
from realestate.api.model_runs import router as model_runs_router
from realestate.api.objects import router as objects_router
from realestate.config import Settings, get_settings
from realestate.kafka.publisher import PriceMetricsPublisher
from realestate.ml.loader import download_model_artifact
from realestate.ml.predict import ModelHolder
from realestate.persistence.mongo import MongoClient
from realestate.persistence.postgres import ModelRegistryRepo, PostgresClient
from realestate.worker import RealestateWorker

configure_logging("realestate")
configure_tracing("realestate")
logger = logging.getLogger(__name__)


async def _load_active_model(
    settings: Settings, registry: ModelRegistryRepo, holder: ModelHolder
) -> tuple[UUID, str] | None:
    try:
        row = await registry.get_active(settings.model_kind)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось обратиться к core.model_registry; модель не загружена.")
        return None
    if not row:
        logger.warning("В core.model_registry нет активной модели task=%s.", settings.model_kind)
        return None
    artifact = download_model_artifact(
        settings,
        minio_path=row["minio_path"],
        version=row["version"],
        model_id=str(row["id"]),
    )
    holder.load(artifact)
    logger.info("Модель загружена: task=%s version=%s", settings.model_kind, row["version"])
    return row["id"], row["version"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    mongo = MongoClient(settings)
    postgres = PostgresClient(settings)
    publisher = PriceMetricsPublisher(settings)
    model_holder = ModelHolder()

    app.state.mongo = mongo
    app.state.postgres = postgres
    app.state.publisher = publisher
    app.state.model_holder = model_holder
    app.state.worker = None
    app.state.rabbit = None

    try:
        await publisher.start()
    except Exception:  # noqa: BLE001
        logger.exception("Kafka producer не стартанул — метрики писать не будем.")

    registry = ModelRegistryRepo(postgres)
    loaded = await _load_active_model(settings, registry, model_holder)

    # Rabbit-соединение нужно и API (POST /model-runs) и worker'у — держим одно.
    try:
        app.state.rabbit = await aio_pika.connect_robust(settings.rabbitmq_url)
    except Exception:  # noqa: BLE001
        logger.exception("RabbitMQ недоступен — POST /api/model-runs будет 503.")

    if loaded and settings.enable_worker_on_startup and model_holder.is_loaded and app.state.rabbit:
        active_model_id, active_model_version = loaded
        worker = RealestateWorker(
            settings=settings,
            mongo=mongo,
            postgres=postgres,
            model_holder=model_holder,
            publisher=publisher,
            active_model_id=active_model_id,
            active_model_version=active_model_version,
        )
        try:
            await worker.start()
            app.state.worker = worker
        except Exception:  # noqa: BLE001
            logger.exception("Worker не стартанул.")

    try:
        yield
    finally:
        if app.state.worker is not None:
            await app.state.worker.stop()
        if app.state.rabbit is not None:
            await app.state.rabbit.close()
        await publisher.stop()
        await postgres.close()
        await mongo.close()


app = FastAPI(title="AIS realestate", version="0.1.0", lifespan=lifespan)
instrument_app(app, "realestate")
app.include_router(objects_router)
app.include_router(model_runs_router)


@app.get("/healthz", tags=["health"])
async def healthz():
    holder: ModelHolder = app.state.model_holder
    return {
        "status": "ok",
        "model_loaded": holder.is_loaded,
        "model_version": holder.artifact.version if holder.artifact else None,
        "worker": app.state.worker is not None,
    }
