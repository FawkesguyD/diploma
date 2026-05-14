FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app \
    HOST=0.0.0.0 \
    PORT=8000 \
    UVICORN_WORKERS=1 \
    MODEL_PATH=/app/ml/artifacts/best_model_russia2021.joblib \
    MODEL_READINESS_PATH=/app/ml/artifacts/model_readiness.json \
    DATABASE_URL=postgresql+psycopg://realestate:realestate@postgres:5432/realestate

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        pandas \
        numpy \
        scipy \
        joblib \
        requests \
        fastapi \
        uvicorn \
        "httpx<0.28" \
        sqlalchemy \
        alembic \
        "psycopg[binary]" \
        itsdangerous \
        six \
    && python -m pip install --no-deps catboost

COPY apps ./apps
COPY ml ./ml
COPY shared ./shared
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "from urllib.request import urlopen; import os; urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/health').read()"

CMD ["sh", "-c", "uvicorn apps.api.api:app --host ${HOST} --port ${PORT} --workers ${UVICORN_WORKERS}"]
