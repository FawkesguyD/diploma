# Локальный запуск

## Python dependencies

```bash
python -m pip install -r requirements.txt
```

## Запуск API

Канонический запуск:

```bash
uvicorn apps.api.api:app --host 0.0.0.0 --port 8000
```

Совместимый запуск:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

API при старте prediction/health загружает active model через:

- `MODEL_READINESS_PATH`, default `ml/artifacts/model_readiness.json`;
- `MODEL_PATH`, default `ml/artifacts/best_model_russia2021.joblib`.

## Запуск полного local stack

```bash
docker compose up --build
```

Compose поднимает:

- PostgreSQL;
- data migrator;
- API;
- UI;
- geocode service.

## Запуск ML pipeline

Канонический запуск:

```bash
python -m ml.model.main --pipeline russia2021
```

Совместимый запуск:

```bash
python main.py --pipeline russia2021
```

Отладочный запуск на ограничении строк:

```bash
python -m ml.model.main --pipeline russia2021 --russia-max-rows 50000
```

Обучение из нормализованной БД:

```bash
python -m ml.model.main --pipeline db_russia2021 --db-training-limit 50000
```

## Тесты

```bash
python -m unittest discover tests
```

Contract tests проверяют:

- RUB-only prediction contract;
- aliases между старой и новой схемой;
- log target inverse transform;
- readiness manifest;
- API response compatibility.

## Demo user

`services/data_migrator/bootstrap.py` создаёт demo user:

- email: `investor@example.com`;
- password: `demo12345`.

Значения можно переопределить через `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`, `DEMO_USER_NAME`.
