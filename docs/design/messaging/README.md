# Messaging — контракты RabbitMQ и Kafka

> **Зачем этот документ:** зафиксировать форматы сообщений между сервисами так, чтобы потоки 2 (разработка модулей) и 3 (инфра) не блокировали друг друга. Сервисы общаются только через эти контракты — никаких прямых вызовов «соседа» по HTTP, кроме случаев, явно описанных в OpenAPI.

## Разделение брокеров (см. [ADR-0002](../../decisions/0002-rabbitmq-and-kafka.md))

| Брокер | Что несёт | Гарантии | Кто пишет / читает |
|---|---|---|---|
| **RabbitMQ** | команды между сервисами (запусти парсинг, проанализируй сообщение, оцени объект) | at-least-once, ack/requeue, DLQ | бэкенд-сервисы |
| **Kafka** | бизнес-метрики рынка (для ClickHouse-дашбордов) | durable, replay-able, batched consumer | те же сервисы → `metrics`-сервис |

> Служебная телеметрия (latency, queue depth, ошибки сервисов) сюда **не попадает** — это уйдёт в будущий observability-стек (см. [clickhouse.md](../databases/clickhouse.md)).

## Общие принципы

- **Формат:** JSON (UTF-8). Сериализация — Pydantic v2 на отправителе, Pydantic-валидация на получателе.
- **Версионирование:** каждое сообщение содержит поле `schema_version: "v1"`. Минорные совместимые изменения (новые опциональные поля) — без подъёма версии. Несовместимые — `v2` параллельно, период миграции.
- **Идемпотентность:** обязательное `message_id` (UUID) у каждого сообщения. Консьюмер обязан хранить `processed_message_ids` (короткий TTL Redis/Mongo) и пропускать дубли — RabbitMQ at-least-once это требует.
- **Корреляция:** `correlation_id` (UUID) — пробрасывается через всю цепочку (parse → nlp → metrics) для трассировки. Если не задан — генерируется на входе и логируется.
- **Время:** все timestamp-поля — ISO-8601 в UTC (`2026-05-14T10:00:00Z`).
- **Размер:** хард-лимит payload — 256 KB. Большие данные (тексты, бинарники) **не передаются** в сообщении — передаётся ссылка (Mongo `_id`, MinIO-ключ).

---

## RabbitMQ — топология

```
Exchanges (все типа topic):
  parser.exchange       — задачи парсинга (publisher: scheduler/UI)
  nlp.exchange          — задачи NLP-анализа (publisher: parser-сервис)
  realestate.exchange   — задачи оценки (publisher: parser-сервис, UI)

Queues:
  parse.task.tg                ← parser.exchange   ключ: parse.task.tg
  parse.task.news              ← parser.exchange   ключ: parse.task.news
  parse.task.realestate        ← parser.exchange   ключ: parse.task.realestate
  nlp.analyze                  ← nlp.exchange      ключ: nlp.analyze
  realestate.score             ← realestate.exchange ключ: realestate.score
  realestate.rank              ← realestate.exchange ключ: realestate.rank

DLQ (для каждой очереди):
  <queue>.dlq                  ← dlx.exchange      max_retries=3
```

**Почему topic, а не direct:** позволяет позже добавить «зеркальные» консьюмеры (например, аудит-сервис подписывается на `parse.task.*` не вмешиваясь в основной поток).

**DLQ-политика:** 3 повтора с экспоненциальной задержкой (5s → 30s → 5min) через `x-delayed-message`, после — в `<queue>.dlq`. Ручной разбор админом.

---

## RabbitMQ — контракты сообщений

Каждое сообщение наследует общий «конверт»:

```jsonc
{
  "schema_version": "v1",
  "message_id":     "uuid",
  "correlation_id": "uuid",
  "issued_at":      "2026-05-14T10:00:00Z",
  "payload":        { /* специфика — ниже */ }
}
```

Дальше описывается только `payload` для каждой очереди.

### `parse.task.tg` — спарсить Telegram-канал

```jsonc
{
  "source_id":   "uuid",          // core.sources.id, kind='tg'
  "since":       "2026-05-14T09:00:00Z",  // опц., иначе с last_polled_at
  "limit":       200,             // опц., max сообщений за раз
  "triggered_by": "schedule"      // 'schedule' | 'manual' | 'backfill'
}
```

Консьюмер: `nlp-parser` сервис. На успех — публикует одно или несколько `nlp.analyze` (по одному на новое сообщение).

### `parse.task.news` — спарсить новостной источник

```jsonc
{
  "source_id":   "uuid",          // kind='news' | 'rss' | 'html'
  "since":       "2026-05-14T09:00:00Z",
  "triggered_by": "schedule"
}
```

### `parse.task.realestate` — спарсить площадку с объявлениями

```jsonc
{
  "source_id":   "uuid",          // kind='realestate_site' (cian/avito/...)
  "filters": {                    // опц., поисковые параметры площадки
    "city":      "Moscow",
    "rooms":     [1, 2, 3],
    "price_max": 30000000
  },
  "triggered_by": "schedule"
}
```

Консьюмер: `realestate` сервис → парсит → пишет в `objects` (Mongo) → публикует `realestate.score` (батч).

### `nlp.analyze` — проанализировать сообщение

Публикуется парсером после сохранения сырого сообщения в `messages`.

```jsonc
{
  "message_id":  "65f8a1b2c3d4e5f6a7b8c9d0",  // ObjectId сообщения в Mongo
  "lang_hint":   "ru",            // опц., если парсер уже определил
  "force":       false            // если true — переразобрать даже при наличии active annotation
}
```

Консьюмер: `nlp-parser` (NLP-под-сервис) → запускает классификатор/NER/sentiment/ad_filter → пишет `annotated_messages` → публикует метрику в Kafka `metrics.messages`.

### `realestate.score` — оценить объект (или батч)

```jsonc
{
  "object_ids": [                 // Mongo ObjectId как hex-строки
    "65f8a1b2c3d4e5f6a7b8c9d0",
    "65f8a1b2c3d4e5f6a7b8c9d1"
  ],
  "model_version": "v1.0",        // опц., иначе active из core.model_registry
  "force":         false
}
```

Консьюмер: `realestate` сервис → инференс CatBoost → `annotated_objects` → метрика в Kafka `metrics.prices`. После завершения батча — публикует `realestate.rank` (если в задаче ≥ 10 объектов).

### `realestate.rank` — пересчитать ранжирование

```jsonc
{
  "model_run_id": "uuid",         // ops.model_runs.id — какой запуск ранжировать
  "scope": {                      // что ранжировать
    "city": "Moscow",
    "district_slug": null,        // null = все районы
    "since": "2026-05-07T00:00:00Z"
  }
}
```

Консьюмер: `realestate` → пересчитывает `rank_in_run` в `annotated_objects` → обновляет дашборд «топ недооценённых».

---

## Kafka — топики

| Топик | Партиций | Retention | Ключ партиционирования | Продьюсер | Консьюмер |
|---|---|---|---|---|---|
| `metrics.messages` | 3 | 7 дней | `source_id` | nlp-parser | metrics |
| `metrics.prices` | 3 | 7 дней | `object_id` | realestate | metrics |

> Retention 7 дней — это окно для «пересобрать ClickHouse из Kafka, если упал consumer». Долгосрочное хранение — уже в ClickHouse (24–36 мес. TTL).

Партиций 3 — достаточно для одного хоста, можно поднять при нагрузке. Ключ выбран так, чтобы события одного источника/объекта попадали в одну партицию (порядок гарантирован внутри партиции).

---

## Kafka — контракты сообщений

Конверт такой же, как у RabbitMQ (`schema_version`, `message_id`, `correlation_id`, `issued_at`, `payload`). Дублирование удобно: один Pydantic-модуль на оба брокера.

### `metrics.messages` — «обработано сообщение»

Один Kafka-message ↔ одна строка в ClickHouse `events_messages`. Поля совпадают со схемой таблицы.

```jsonc
{
  "event_time":      "2026-05-14T10:00:42Z",
  "published_at":    "2026-05-14T10:00:00Z",

  "message_id":      "65f8a1b2c3d4e5f6a7b8c9d0",
  "source_id":       "uuid",
  "channel_kind":    "tg",
  "channel_site":    "t.me",

  "topic_slug":      "badaevsky_complex",
  "topic_score":     0.91,
  "topics_all":      ["badaevsky_complex", "mortgage_rates"],

  "sentiment_label": "neutral",
  "sentiment_score": 0.62,

  "is_ad":           false,
  "lang":            "ru",

  "entities_districts":  ["presnenskiy"],
  "entities_developers": ["Capital Group"],

  "model_run_id":    "uuid"
}
```

### `metrics.prices` — «оценили объект»

Один Kafka-message ↔ одна строка в ClickHouse `events_prices`.

```jsonc
{
  "event_time":      "2026-05-14T10:05:00Z",
  "published_at":    "2026-05-13T08:00:00Z",

  "object_id":       "65f8a1b2c3d4e5f6a7b8c9d1",
  "source_id":       "uuid",
  "object_kind":     "residential",
  "channel_site":    "cian.ru",
  "city":            "Moscow",
  "district_slug":   "presnenskiy",

  "rooms":           2,
  "area":            52.4,
  "floor":           7,
  "year_built":      2008,

  "price_real":      14500000,
  "price_predicted": 16200000,
  "deviation_abs":   -1700000,
  "deviation_pct":   -10.49,
  "is_undervalued":  true,
  "rank_in_run":     3,

  "model_version":   "v1.0",
  "model_run_id":    "uuid"
}
```

---

## Диаграмма потоков (упрощённо)

```
                   ┌────────────────────────────────────────────────┐
scheduler/UI  ──►  │ RabbitMQ                                       │
                   │  parse.task.tg ─►  nlp-parser                   │
                   │  parse.task.news ─► nlp-parser                  │
                   │                       │                         │
                   │                       ▼ (per msg)               │
                   │  nlp.analyze ──────► nlp-parser (NLP step)      │
                   │                       │                         │
                   │  parse.task.realestate ─► realestate            │
                   │                              │                  │
                   │                              ▼ (batch)          │
                   │  realestate.score ───────► realestate           │
                   │  realestate.rank  ───────► realestate           │
                   └────────────────────────────────────────────────┘
                              │                         │
                              ▼ metrics.messages        ▼ metrics.prices
                   ┌────────────────────────────────────────────────┐
                   │ Kafka                                           │
                   └────────────────────────────────────────────────┘
                                          │
                                          ▼ batch consume
                                      metrics-сервис
                                          │
                                          ▼ batch insert
                                      ClickHouse
```

## Решения по реализации

- **Retry в RabbitMQ — через плагин `rabbitmq_delayed_message_exchange`.** Альтернатива (городить вручную `*.retry`-очереди с TTL + DLX) — это пять-десять строк лишней YAML-топологии на каждую боевую очередь и шанс ошибиться в TTL. Плагин даёт `x-delayed-message` exchange, в который публикуется сообщение с заголовком `x-delay: <ms>` — брокер сам подождёт указанное время, потом отправит в основную очередь. Активируется в `Dockerfile` для RabbitMQ через `rabbitmq-plugins enable rabbitmq_delayed_message_exchange`.

- **Schema registry для Kafka — не используем.** Confluent/Apicurio оправданы, когда (а) продьюсеры и консьюмеры на разных языках или (б) сторонние команды читают наши топики. У нас всё на Python, все сервисы импортируют общий пакет `services/_shared/contracts/` с Pydantic-моделями — это и есть «registry», только с типизацией на этапе компиляции (mypy/pyright) и автодополнением в IDE. Если позже добавится сервис на другом языке — поднимем Apicurio с JSON-Schema, экспортированной из тех же Pydantic-моделей (`model_json_schema()`).
