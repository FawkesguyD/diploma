FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

COPY requirements.txt .

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY apps/normalization ./apps/normalization
COPY apps/geocode ./apps/geocode
COPY ml ./ml
COPY shared ./shared
COPY services ./services

CMD ["python", "-m", "services.data_migrator"]
