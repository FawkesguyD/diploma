from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI

from nlp_parser.api.auth import router as auth_router
from nlp_parser.api.favorites import router as favorites_router
from nlp_parser.api.jobs import router as jobs_router
from nlp_parser.api.messages import router as messages_router
from nlp_parser.api.sources import router as sources_router
from nlp_parser.api.subscriptions import router as subscriptions_router
from nlp_parser.api.trends import router as trends_router
from nlp_parser.config import get_settings
from nlp_parser.kafka_publisher import MessageMetricsPublisher
from nlp_parser.persistence.mongo import MongoClient
from nlp_parser.persistence.postgres import PostgresClient
from nlp_parser.pubsub import MessagePubSub
from nlp_parser.worker import NlpParserWorker
from aisi_obs import configure_logging, configure_tracing, instrument_app

configure_logging("nlp-parser")
configure_tracing("nlp-parser")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    mongo = MongoClient(settings)
    postgres = PostgresClient(settings)
    publisher = MessageMetricsPublisher(settings)
    pubsub = MessagePubSub()

    app.state.mongo = mongo
    app.state.postgres = postgres
    app.state.publisher = publisher
    app.state.pubsub = pubsub
    app.state.rabbit = None
    app.state.worker = None

    try:
        await publisher.start()
    except Exception:
        logger.exception("Kafka producer не стартанул — метрики писать не будем.")

    try:
        app.state.rabbit = await aio_pika.connect_robust(settings.rabbitmq_url)
    except Exception:
        logger.exception("RabbitMQ недоступен — worker не стартует.")

    if settings.enable_worker_on_startup and app.state.rabbit is not None:
        worker = NlpParserWorker(
            settings=settings,
            mongo=mongo,
            postgres=postgres,
            publisher=publisher,
            pubsub=pubsub,
        )
        try:
            await worker.start()
            app.state.worker = worker
        except Exception:
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


app = FastAPI(title="AIS nlp-parser", version="0.1.0", lifespan=lifespan)
instrument_app(app, "nlp-parser")
app.include_router(auth_router)
app.include_router(sources_router)
app.include_router(messages_router)
app.include_router(subscriptions_router)
app.include_router(favorites_router)
app.include_router(trends_router)
app.include_router(jobs_router)


@app.get("/healthz", tags=["health"])
async def healthz():
    return {
        "status": "ok",
        "worker": app.state.worker is not None,
        "kafka": app.state.publisher.is_started,
    }
