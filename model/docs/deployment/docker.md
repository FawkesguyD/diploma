# Docker

## Compose stack

`docker-compose.yml` поднимает:

| Service | Назначение | Порт |
| --- | --- | --- |
| `postgres` | PostgreSQL 16 | `${POSTGRES_PORT:-5432}` |
| `data-migrator` | Alembic migrations, CSV import, valuation seed | one-shot |
| `real-estate-api` | основной FastAPI API | `${API_PORT:-8000}` |
| `real-estate-ui` | React UI через nginx | `${UI_PORT:-5173}` |
| `geocode-service` | отдельный geocode FastAPI app | `${GEOCODE_PORT:-8081}` -> `8080` |
| `analytics-service` | отдельный FastAPI сервис `/score` | `${ANALYTICS_PORT:-8090}` -> `8090` |

Запуск:

```bash
docker compose up --build
```

## API image

Канонический Dockerfile: `apps/api/Dockerfile`.

Он копирует:

- `apps`;
- `ml`;
- `shared`;
- `alembic`;
- `alembic.ini`.

Default runtime env:

- `MODEL_PATH=/app/ml/artifacts/best_model_russia2021.joblib`;
- `MODEL_READINESS_PATH=/app/ml/artifacts/model_readiness.json`;
- `DATABASE_URL=postgresql+psycopg://realestate:realestate@postgres:5432/realestate`.

Healthcheck вызывает `GET /health`, поэтому проверяет не только процесс, но и загрузку active model.

## Data migrator image

Dockerfile: `services/data_migrator/Dockerfile`.

Мигратор:

1. ждёт PostgreSQL;
2. запускает Alembic migrations;
3. импортирует `office-sale.csv`;
4. нормализует raw rows;
5. вызывает `ensure_listing_valuations`;
6. создаёт demo user.

## UI image

Dockerfile: `apps/ui/Dockerfile`.

UI ожидает API base URL из build arg `VITE_API_BASE_URL`, default `/api`.

## Geocode image

Dockerfile: `apps/geocode/Dockerfile`.

Сервис использует Nominatim-compatible provider и отдельные env vars `GEOCODER_*`.

## Analytics image

Dockerfile: `apps/analytics_service/Dockerfile`.

Сервис предоставляет `POST /score?method=price_per_meter|formula|regression`. Для `regression` он использует существующий runtime inference и те же переменные:

- `MODEL_PATH=/app/ml/artifacts/best_model_russia2021.joblib`;
- `MODEL_READINESS_PATH=/app/ml/artifacts/model_readiness.json`.

Методы `price_per_meter` и `formula` не требуют загрузки ML-артефакта. Валютный режим сервиса — только `RUB`; FX в этом MVP-сервисе не поддерживается.

## Корневой Dockerfile

Корневой `Dockerfile` сохранён как совместимый API image для старых сценариев. Канонический для API — `apps/api/Dockerfile`.
