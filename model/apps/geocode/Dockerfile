FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app \
    HOST=0.0.0.0 \
    PORT=8080 \
    GEOCODER_PROVIDER=nominatim \
    GEOCODER_BASE_URL=https://nominatim.openstreetmap.org/search \
    GEOCODER_REVERSE_BASE_URL=https://nominatim.openstreetmap.org/reverse \
    GEOCODER_TIMEOUT=10 \
    GEOCODER_USER_AGENT="real-estate-mvp-geocode/0.1 (local development)"

WORKDIR ${APP_HOME}

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        fastapi \
        uvicorn \
        "httpx<0.28"

COPY apps/__init__.py ./apps/__init__.py
COPY apps/geocode ./apps/geocode

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; import os; urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8080\")}/health').read()"

CMD ["sh", "-c", "uvicorn apps.geocode.api:app --host ${HOST} --port ${PORT}"]
