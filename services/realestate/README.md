# services/realestate

FastAPI-сервис модуля «Недвижимость» дипломного АИС. Поток 2.1 плана —
оборачивает научную модель из [`/model`](../../model) в боевой сервис.

## Что делает

* `/api/objects/*` — REST для UI: список объектов (cursor-пагинация), детальный
  просмотр, история цены, топ недооценённых (см. `docs/design/api/README.md`).
* `/api/model-runs/*` — журнал запусков и ручной триггер `realestate.score`.
* RabbitMQ-worker подписан на `parse.task.realestate`, `realestate.score` и
  `realestate.rank` (топология — `infra/rabbitmq/definitions.json`):
  parse → upsert в Mongo `objects` → автопубликация `realestate.score` →
  инференс → `annotated_objects` + Kafka `metrics.prices` → rank.
* По каждому оценённому объекту публикует `PriceMetric` в Kafka
  `metrics.prices` для дашбордов (ClickHouse через metrics-сервис).

## Стек

Python 3.11 · FastAPI · Pydantic v2 · Motor · SQLAlchemy[asyncpg] ·
aio-pika · aiokafka · MinIO · CatBoost (через `model.ml.model.inference`).

## Контракты

Pydantic-модели, общие с другими сервисами — в
[`services/_shared/contracts`](../_shared/contracts) (`aisi-contracts`).
Здесь же лежит `Envelope` из messaging-спеки.

## Конфигурация (env)

Перечень переменных см. `realestate/config.py`. Базовые значения берутся
из корневого `.env` (см. `.env.example`).

## Запуск в составе compose

```bash
docker compose build realestate
docker compose up -d realestate
```

Health-чек: `GET http://localhost:8000/healthz`. Через Traefik — пути
`/api/objects/*` и `/api/model-runs/*`.

## Переиспользование `model/`

В Dockerfile копируем только `model/ml/` под `/app/vendor/model/ml/` и
прокидываем в `PYTHONPATH`. Импорты в коде:

* `model.ml.model.inference.predict_proxy_valuation_from_bundle`
* `model.ml.model.persistence.load_model_bundle`

Обучающие скрипты, ноутбуки, аналитика — не копируются.

## TODO / known gaps

* Идемпотентность `processed_message_ids` — пока in-memory; для нескольких
  реплик надо вынести в Redis/Mongo с TTL.
* SSE/poll эндпоинт `/api/jobs` — будет общим (см. `api/README.md`).
* `parsing/stub.py` — мок-парсер с fixture-данными; реальные адаптеры
  CIAN/Avito/DomClick подключаются как отдельные реализации `parse_source`.
