# syntax=docker/dockerfile:1.7
# =====================================================================
# realestate service: FastAPI + RabbitMQ worker.
# Multi-stage build с uv для установки зависимостей.
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

# uv (ставим из PyPI — ghcr.io/astral-sh/uv требует auth)
RUN pip install --no-cache-dir "uv>=0.5,<0.6"

WORKDIR /opt/build

# Сначала ставим shared contracts (editable не нужен в проде, копируем как пакет).
COPY services/_shared/contracts /opt/build/_shared/contracts
COPY services/_shared/redis_lib /opt/build/_shared/redis_lib
COPY services/realestate/pyproject.toml /opt/build/realestate/pyproject.toml

# Создаём venv и ставим зависимости.
RUN uv venv /opt/venv \
 && . /opt/venv/bin/activate \
 && uv pip install --python /opt/venv/bin/python /opt/build/_shared/contracts \
 && uv pip install --python /opt/venv/bin/python /opt/build/_shared/redis_lib \
 && uv pip install --python /opt/venv/bin/python \
        "fastapi>=0.110" "uvicorn[standard]>=0.27" \
        "pydantic>=2.6" "pydantic-settings>=2.2" \
        "motor>=3.4" "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.29" \
        "aio-pika>=9.4" "aiokafka>=0.10" \
        "minio>=7.2" "catboost>=1.2" "joblib>=1.3" \
        "numpy>=1.26" "pandas>=2.1" "scikit-learn>=1.3" \
        "httpx>=0.27" "orjson>=3.10" "redis>=5.0"

# ---------- runtime ---------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/src:/app/vendor"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system app \
 && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Исходники сервиса.
COPY services/realestate/src /app/src

# Переиспользуем инференс-пайплайн из научной части (read-only).
# Ставим под /app/vendor/model/... — путь импорта `model.ml.model.inference`.
COPY model/ml /app/vendor/model/ml
RUN touch /app/vendor/model/__init__.py

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "realestate.main:app", "--host", "0.0.0.0", "--port", "8000"]
