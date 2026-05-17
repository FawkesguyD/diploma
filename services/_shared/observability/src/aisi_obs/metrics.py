"""Prometheus metrics via prometheus-fastapi-instrumentator."""
from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def instrument_app(app: FastAPI, service: str) -> None:
    """Attach Prometheus /metrics endpoint and auto-instrument all routes."""
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/healthz", "/metrics"],
        env_var_name="ENABLE_METRICS",
        body_handlers=[],
    ).instrument(app).expose(app, include_in_schema=False, tags=["observability"])
