"""Structured JSON logging with trace_id injection."""
from __future__ import annotations

import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter


class _TraceContextFilter(logging.Filter):
    """Injects trace_id and span_id from the active OpenTelemetry span."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace as _trace
            span = _trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id  = format(ctx.span_id,  "016x")
            else:
                record.trace_id = ""
                record.span_id  = ""
        except Exception:  # noqa: BLE001
            record.trace_id = ""
            record.span_id  = ""
        return True


def configure_logging(service: str, level: str | None = None) -> None:
    """Set up JSON logging for the given service name.

    Reads LOG_LEVEL env var (default INFO). Emits records as JSON so
    Promtail can parse them and extract level / trace_id / user_id labels.
    """
    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    fmt = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level", "name": "logger", "message": "msg"},
        static_fields={"service": service},
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    handler.addFilter(_TraceContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Keep noisy libraries quieter
    for noisy in ("uvicorn.access", "aiokafka", "aio_pika", "motor"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
