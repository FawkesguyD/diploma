# ClickHouse — схема аналитического хранилища

> **Назначение БД:** метрики и агрегаты для дашбордов. Append-only, тяжёлые `GROUP BY` по большому объёму. **НЕ** для оперативных данных (сообщений, объявлений) — это в MongoDB.

## Зоны ответственности

1. **Сырые события (raw)** — то, что прилетает в Kafka и пишется батчами. Источник правды для всех агрегатов, можно «пересобрать всё с нуля».
2. **Агрегаты (materialized views)** — заранее посчитанные срезы для быстрого ответа дашбордам.
3. **Справочники (Dictionaries)** — топики, районы, источники, модели — подтягиваются из Postgres через ODBC/HTTP-словари.

## Принципы

- **`MergeTree`-семейство** для всех таблиц. Партиционирование `toYYYYMM(event_time)` (если иное не указано).
- Ключ сортировки — `(event_time, …)`, наиболее селективные поля идут раньше времени **только** если они высокоселективные.
- **Materialized views** считают агрегаты на лету (`AggregatingMergeTree`/`SummingMergeTree`).
- **Dictionaries** для джойнов со справочниками (топики, районы) — без копирования данных.
- Запись только **батчами** через сервис `metrics` (Kafka consumer → batch insert), никаких пер-row inserts.
- Имя таблиц/полей — `snake_case`.

---

## Топики Kafka → таблицы

| Kafka topic | Источник | Целевая таблица |
|---|---|---|
| `metrics.messages` | nlp-parser | `events_messages` |
| `metrics.prices` | realestate | `events_prices` |
| `metrics.system` | все сервисы | `events_system` |

---

## Таблица `events_messages` — событие «обработано сообщение»

Одна строка = одно сообщение прошло через NLP-пайплайн.

```sql
CREATE TABLE events_messages
(
    event_time      DateTime64(3) CODEC(Delta, ZSTD),
    published_at    DateTime64(3),

    message_id      String,            -- ссылка на MongoDB messages._id
    source_id       UUID,              -- ссылка на Postgres sources.id
    source_kind     LowCardinality(String),  -- 'telegram' | 'rss' | ...

    topic_slug      LowCardinality(String),  -- первичная тема (топ-1 от классификатора)
    topic_score     Float32,
    topics_all      Array(LowCardinality(String)),  -- все темы (для гибких запросов)

    sentiment_label LowCardinality(String),  -- 'positive' | 'neutral' | 'negative'
    sentiment_score Float32,

    is_ad           UInt8,             -- 0/1
    lang            LowCardinality(String),

    entities_districts Array(LowCardinality(String)),  -- slug-и районов в сообщении
    entities_developers Array(String),

    model_run_id    UUID
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (source_kind, topic_slug, event_time)
TTL event_time + INTERVAL 24 MONTH;
```

**Зачем поля дублируются (топик и slug в Postgres):** в ClickHouse дешевле читать `LowCardinality(String)`, чем джойниться по UUID на каждую агрегацию. Источник правды — Postgres + Mongo, ClickHouse — денормализованный слепок.

---

## Таблица `events_prices` — событие «оценили объявление»

```sql
CREATE TABLE events_prices
(
    event_time       DateTime64(3) CODEC(Delta, ZSTD),
    published_at     DateTime64(3),

    listing_id       String,            -- ссылка на MongoDB realestate_listings._id
    source_id        UUID,
    city             LowCardinality(String),
    district_slug    LowCardinality(String),

    rooms            UInt8,
    area             Float32,
    floor            UInt8,
    year_built       UInt16,

    price_real       Float64,
    price_predicted  Float64,
    deviation_abs    Float64,
    deviation_pct    Float32,
    is_undervalued   UInt8,
    rank_in_run      UInt32,

    model_version    LowCardinality(String),
    model_run_id     UUID
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (city, district_slug, event_time)
TTL event_time + INTERVAL 36 MONTH;
```

---

## Таблица `events_system` — служебные метрики

Время отклика API, длительность задач парсинга, размер очередей RabbitMQ, и т.п. Используется для технических дашбордов «здоровья» системы.

```sql
CREATE TABLE events_system
(
    event_time DateTime64(3) CODEC(Delta, ZSTD),
    service    LowCardinality(String),  -- 'realestate' | 'nlp-parser' | ...
    metric     LowCardinality(String),  -- 'http.latency_ms' | 'queue.depth' | ...
    labels     Map(LowCardinality(String), String),
    value      Float64
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (service, metric, event_time)
TTL event_time + INTERVAL 6 MONTH;
```

---

## Materialized Views (агрегаты для дашбордов)

### 1. `mv_messages_by_topic_hourly` — активность по темам почасово

> Дашборд: «насколько много сообщений по теме *Бадаевский комплекс* сейчас».

```sql
CREATE MATERIALIZED VIEW mv_messages_by_topic_hourly
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (topic_slug, source_kind, hour)
AS
SELECT
    toStartOfHour(event_time) AS hour,
    topic_slug,
    source_kind,
    count() AS messages_total,
    sumIf(1, is_ad = 0) AS messages_non_ad,
    avg(sentiment_score) AS sentiment_avg,
    countIf(sentiment_label = 'positive') AS pos_count,
    countIf(sentiment_label = 'negative') AS neg_count
FROM events_messages
GROUP BY hour, topic_slug, source_kind;
```

### 2. `mv_prices_timeseries_daily` — динамика цен по районам

> Дашборд: «как изменяются цены во времени».

```sql
CREATE MATERIALIZED VIEW mv_prices_timeseries_daily
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (city, district_slug, day)
AS
SELECT
    toDate(event_time) AS day,
    city,
    district_slug,
    avgState(price_real / area)        AS avg_price_per_m2_state,
    medianState(price_real / area)     AS median_price_per_m2_state,
    avgState(deviation_pct)            AS avg_deviation_pct_state,
    countState()                       AS listings_seen_state
FROM events_prices
WHERE area > 0
GROUP BY day, city, district_slug;
```

> Запрос фронта читает через `avgMerge`, `medianMerge`, `countMerge`.

### 3. `mv_district_activity_daily` — активность покупок по районам

> Дашборд: «в каком районе сейчас лучше покупают жильё». Метрика «покупают лучше» = плотность новых объявлений + средняя величина недооценки.

```sql
CREATE MATERIALIZED VIEW mv_district_activity_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (city, district_slug, day)
AS
SELECT
    toDate(event_time) AS day,
    city,
    district_slug,
    count()                              AS listings_new,
    sumIf(1, is_undervalued = 1)         AS undervalued_count,
    avgIf(deviation_pct, is_undervalued = 1) AS avg_undervaluation_pct
FROM events_prices
GROUP BY day, city, district_slug;
```

### 4. `mv_top_undervalued_weekly` — топ недооценённых за период

Можно считать «на лету» в самом сервисе `metrics` поверх `events_prices` (нет смысла материализовать — выборка маленькая, ad-hoc запрос).

---

## Dictionaries (справочники из Postgres)

Чтобы в UI показывать человекочитаемые имена тем и районов без джойнов в SELECT.

```sql
CREATE DICTIONARY dict_topics
(
    slug         String,
    display_name String,
    parent_slug  String
)
PRIMARY KEY slug
SOURCE(HTTP(url 'http://metrics:8000/internal/dict/topics' format 'JSONEachRow'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED());
```

> Сервис `metrics` экспонирует `/internal/dict/*` эндпоинты, читая из Postgres. Это разрывает прямую зависимость ClickHouse → Postgres.

Аналогично — `dict_districts`, `dict_sources`.

---

## Профиль запросов от UI (примеры)

### «Активность по теме `badaevsky_complex` за последние 7 дней, по часам»

```sql
SELECT hour, sum(messages_non_ad) AS msg
FROM mv_messages_by_topic_hourly
WHERE topic_slug = 'badaevsky_complex'
  AND hour >= now() - INTERVAL 7 DAY
GROUP BY hour
ORDER BY hour;
```

### «Средняя цена за м² по району Пресненский, помесячно»

```sql
SELECT
    toStartOfMonth(day) AS month,
    avgMerge(avg_price_per_m2_state) AS avg_price_per_m2
FROM mv_prices_timeseries_daily
WHERE city = 'Moscow' AND district_slug = 'presnenskiy'
GROUP BY month
ORDER BY month;
```

### «Топ-10 недооценённых объектов за последнюю неделю»

```sql
SELECT listing_id, district_slug, price_real, deviation_pct
FROM events_prices
WHERE event_time >= now() - INTERVAL 7 DAY
  AND is_undervalued = 1
ORDER BY deviation_pct ASC
LIMIT 10;
```

---

## Что НЕ хранится в ClickHouse

- Тексты сообщений → MongoDB.
- Конфиги, пользователи, активная модель → PostgreSQL.
- Бинарники моделей → MinIO.

## Открытые вопросы

- [ ] Партиционирование `mv_*_daily` по месяцу — нормально для 2–3 лет данных. Если планируем больше — перейти на `toYYYYMMDD`.
- [ ] TTL: 24 мес. для сообщений, 36 мес. для цен — достаточно для диплома или хочется больше?
- [ ] Использовать ли `ReplacingMergeTree` для `events_prices` при повторных запусках модели на том же объявлении? Альтернатива — фильтровать «последний `model_run_id`» в запросах.
- [ ] Нужна ли отдельная таблица `events_parser` (длительности парсинга, ошибки) или это идёт в `events_system`?
