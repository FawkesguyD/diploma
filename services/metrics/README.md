# metrics — сервис метрик и дашбордов

Назначение:

1. Слушает Kafka-топики `metrics.messages` и `metrics.prices`, батчами
   пишет в ClickHouse-таблицы `events_messages` / `events_prices`.
2. Отдаёт FastAPI-эндпоинты `/api/dashboards/*` поверх materialized
   views (`mv_*`) — данные для 11 виджетов на стороне фронта.

См. `docs/design/databases/clickhouse.md`,
`docs/design/messaging/README.md`, `docs/design/dashboards.md`.

## Эндпоинты

| Виджет | API эндпоинт | MV |
|---|---|---|
| 1.2 KPI «активность рынка» | `GET /api/dashboards/overview` | `mv_district_activity_daily` + `mv_messages_by_topic_hourly` |
| 2.1 Динамика цен | `GET /api/dashboards/prices/timeseries` | `mv_prices_timeseries_daily` |
| 2.2 Распределение по комнатности | `GET /api/dashboards/prices/distribution` | `mv_price_distribution_by_rooms_monthly` |
| 2.3 Цены по районам | `GET /api/dashboards/prices/by-district` | `mv_prices_timeseries_daily` |
| 3.1 Активность по теме | `GET /api/dashboards/topics/activity` | `mv_messages_by_topic_hourly` |
| 3.2 Тональность по районам | `GET /api/dashboards/sentiment/by-district` | `mv_sentiment_by_district_daily` |
| 3.3 Связи тем | `GET /api/dashboards/topics/cooccurrence` | `mv_topic_cooccurrence_daily` |
| 4.1 MAE deviation | `GET /api/dashboards/model-quality` | `mv_model_quality_daily` |
| 4.2 Доля недооценённых | `GET /api/dashboards/model-quality/undervalued-share` | `mv_model_quality_daily` |
| 5.1 Поток объектов по площадкам | `GET /api/dashboards/listings/by-channel` | `mv_listings_by_channel_daily` |
| 1.1 Топ недооценённых | `GET /api/dashboards/objects/top-undervalued` | ad-hoc на `events_prices` |

## Конфиг (env)

* `CLICKHOUSE_URL` / `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` / `CLICKHOUSE_DB`
* `KAFKA_BOOTSTRAP`
* `BATCH_SIZE`, `BATCH_TIMEOUT_S`

## Кэш

In-memory LRU+TTL, TTL = `granularity / 2` (см. `dashboards.md`).
