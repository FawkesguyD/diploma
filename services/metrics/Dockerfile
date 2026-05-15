# syntax=docker/dockerfile:1.7
# =====================================================================
# metrics service: Kafka consumer (metrics.messages, metrics.prices)
# + FastAPI dashboards API (/api/dashboards/*) поверх ClickHouse.
# =====================================================================

ARG PYTHON_VERSION=3.11

# ---------- builder ---------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.5,<0.6"

WORKDIR /opt/build

# Сначала ставим shared contracts, потом — зависимости сервиса.
COPY services/_shared/contracts /opt/build/_shared/contracts
COPY services/metrics/pyproject.toml /opt/build/metrics/pyproject.toml

RUN uv venv /opt/venv \
 && . /opt/venv/bin/activate \
 && uv pip install --python /opt/venv/bin/python /opt/build/_shared/contracts \
 && uv pip install --python /opt/venv/bin/python \
        "fastapi>=0.110" "uvicorn[standard]>=0.27" \
        "pydantic>=2.6" "pydantic-settings>=2.2" \
        "aiokafka>=0.10" "clickhouse-connect>=0.7" "aiohttp>=3.9" \
        "orjson>=3.10"

# ---------- runtime ---------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/src"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system app \
 && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY services/metrics/src /app/src

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "metrics.main:app", "--host", "0.0.0.0", "--port", "8000"]
