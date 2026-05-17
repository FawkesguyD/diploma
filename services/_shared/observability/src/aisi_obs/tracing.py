"""OpenTelemetry tracing: OTLP export to Tempo."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_tracing(service: str) -> None:
    """Bootstrap OpenTelemetry SDK and export traces to Tempo via OTLP/gRPC.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT env var (default http://tempo:4317).
    Set OTEL_TRACES_SAMPLER_ARG=0.0 to disable sampling for tests.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        sample_rate = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        resource = Resource.create({"service.name": service, "service.version": "0.1.0"})
        provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(sample_rate))

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor().instrument()

        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
        except ImportError:
            pass

        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
        except ImportError:
            pass

        logger.info("OpenTelemetry tracing configured service=%s endpoint=%s", service, endpoint)

    except Exception:  # noqa: BLE001
        logger.warning("OpenTelemetry setup failed — tracing disabled", exc_info=True)
