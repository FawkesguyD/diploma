# Runtime config

## API

| Переменная | Default | Значение |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | host uvicorn |
| `PORT` | `8000` | port uvicorn |
| `UVICORN_WORKERS` | `1` | число workers в Docker command |
| `MODEL_PATH` | `ml/artifacts/best_model_russia2021.joblib` локально, `/app/ml/artifacts/best_model_russia2021.joblib` в Docker | configured model path |
| `MODEL_READINESS_PATH` | `ml/artifacts/model_readiness.json` локально, `/app/ml/artifacts/model_readiness.json` в Docker | readiness manifest |
| `DATABASE_URL` | `postgresql+psycopg://realestate:realestate@localhost:5432/realestate` локально | PostgreSQL URL |
| `SESSION_COOKIE_NAME` | `real_estate_session` | имя session cookie |
| `SESSION_SECRET` | `dev-session-secret-change-me` локально | secret для session middleware |
| `SESSION_MAX_AGE_SECONDS` | `43200` | срок session |
| `UI_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | CORS origins |

## Model readiness

`MODEL_PATH` и `MODEL_READINESS_PATH` должны указывать на согласованные файлы. Если `MODEL_PATH` задан явно и не совпадает с `active_model_path` в manifest, API не загрузит модель.

Для переключения модели:

1. Сохраните новый `joblib` в `ml/artifacts`.
2. Обновите `model_readiness.json`.
3. Убедитесь, что `status` равен `ready` или `active`.
4. Убедитесь, что `base_currency` равен `RUB`.
5. Перезапустите API.

## Database

Default local URL задаётся в `shared/db/session.py`:

```text
postgresql+psycopg://realestate:realestate@localhost:5432/realestate
```

Compose использует host `postgres`.

## Data migrator

| Переменная | Default | Значение |
| --- | --- | --- |
| `CSV_SOURCE_PATH` | `./office-sale.csv` | CSV для seed/import |
| `DEMO_USER_NAME` | `Demo Investor` | имя demo user |
| `DEMO_USER_EMAIL` | `investor@example.com` | email demo user |
| `DEMO_USER_PASSWORD` | `demo12345` | пароль demo user |

## Geocode

| Переменная | Default |
| --- | --- |
| `GEOCODER_PROVIDER` | `nominatim` |
| `GEOCODER_BASE_URL` | `https://nominatim.openstreetmap.org/search` |
| `GEOCODER_REVERSE_BASE_URL` | `https://nominatim.openstreetmap.org/reverse` |
| `GEOCODER_TIMEOUT` | `10` |
| `GEOCODER_USER_AGENT` | `real-estate-mvp-geocode/0.1 (local development)` |

## UI

| Переменная/build arg | Default | Значение |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | base URL основного API |
