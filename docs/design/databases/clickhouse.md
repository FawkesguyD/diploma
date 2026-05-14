# ClickHouse — схема аналитического хранилища

> **Назначение БД:** метрики и агрегаты **состояния рынка недвижимости** для дашбордов. Append-only, тяжёлые `GROUP BY` по большому объёму.
>
> **Что сюда НЕ попадает:** служебные метрики системы (latency сервисов, длительность задач, размер очередей, активность пользователей в UI). Это всё уйдёт в **отдельный observability-стек** (Prometheus/Loki/Grafana или аналог), когда будет заведён. Смешивать «бизнес-метрики рынка» и «техническую телеметрию» в одной БД — путать аудиторию данных и усложнять права доступа.

## Зоны ответственности

1. **Сырые рыночные события (raw)** — то, что прилетает в Kafka и пишется батчами. Источник правды для всех агрегатов, можно «пересобрать всё с нуля».
2. **Агрегаты (materialized views)** — заранее посчитанные срезы для быстрого ответа дашбордам по рынку.
3. **Справочники (Dictionaries)** — топики, районы, источники, модели — подтягиваются через HTTP-эндпоинты сервиса `metrics`.

## Принципы

- **`MergeTree`-семейство** для всех таблиц. Партиционирование `toYYYYMMDD(event_time)` — посуточные партиции (см. ADR-обоснование ниже).
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

> Технические метрики (`metrics.system`, `metrics.http`, и т.п.) сюда не идут — они уйдут в observability-стек отдельно.

---

## Таблица `events_messages` — событие «обработано сообщение о рынке»

Одна строка = одно сообщение прошло через NLP-пайплайн. Используется для метрик информационного фона рынка (активность по темам, тональность, упоминания районов/застройщиков).

```sql
CREATE TABLE events_messages
(
    event_time      DateTime64(3) CODEC(Delta, ZSTD),
    published_at    DateTime64(3),

    message_id      String,            -- ссылка на MongoDB messages._id
    source_id       UUID,              -- ссылка на Postgres core.sources.id
    channel_kind    LowCardinality(String),  -- 'tg' | 'news' | 'rss' | 'html'
    channel_site    LowCardinality(String),  -- 't.me' | 'rbc.ru' | ...

    topic_slug      LowCardinality(String),  -- первичная тема (топ-1 от классификатора)
    topic_score     Float32,
    topics_all      Array(LowCardinality(String)),  -- все темы (для гибких запросов)

    sentiment_label LowCardinality(String),  -- 'positive' | 'neutral' | 'negative'
    sentiment_score Float32,

    is_ad           UInt8,             -- 0/1
    lang            LowCardinality(String),

    entities_districts  Array(LowCardinality(String)),  -- slug-и районов в сообщении
    entities_developers Array(String),

    model_run_id    UUID
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (channel_kind, topic_slug, event_time)
TTL event_time + INTERVAL 24 MONTH;
```

**Зачем поля дублируются (slug-и из Postgres/Mongo):** в ClickHouse дешевле читать `LowCardinality(String)`, чем джойниться по UUID на каждую агрегацию. Источник правды — Postgres + Mongo, ClickHouse — денормализованный слепок.

---

## Таблица `events_prices` — событие «оценили объект»

```sql
CREATE TABLE events_prices
(
    event_time       DateTime64(3) CODEC(Delta, ZSTD),
    published_at     DateTime64(3),

    object_id        String,            -- ссылка на MongoDB objects._id
    source_id        UUID,
    object_kind      LowCardinality(String),  -- 'residential' | 'commercial' | ...
    channel_site     LowCardinality(String),  -- 'cian.ru' | 'avito.ru' | ...
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
ENGINE = ReplacingMergeTree(event_time)
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (object_id, model_version)
TTL event_time + INTERVAL 36 MONTH;
```

> **Почему `ReplacingMergeTree` по `(object_id, model_version)`:** при повторных запусках модели той же версии на том же объекте (бывает при backfill / переразборе) дубли схлопываются в фоне по самому свежему `event_time`. Разные версии модели сосуществуют — это нужно для `mv_model_quality_daily` (сравнение версий). Запросы, которым важна точная актуальность, используют модификатор `FINAL` или `argMax(... , event_time)`.

---

## Materialized Views (агрегаты для дашбордов рынка)

### 1. `mv_messages_by_topic_hourly` — активность по темам почасово

> Дашборд: «насколько много сообщений по теме *Бадаевский комплекс* сейчас».

```sql
CREATE MATERIALIZED VIEW mv_messages_by_topic_hourly
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(hour)
ORDER BY (topic_slug, channel_kind, hour)
AS
SELECT
    toStartOfHour(event_time) AS hour,
    topic_slug,
    channel_kind,
    count() AS messages_total,
    sumIf(1, is_ad = 0) AS messages_non_ad,
    avg(sentiment_score) AS sentiment_avg,
    countIf(sentiment_label = 'positive') AS pos_count,
    countIf(sentiment_label = 'negative') AS neg_count
FROM events_messages
GROUP BY hour, topic_slug, channel_kind;
```

### 2. `mv_prices_timeseries_daily` — динамика цен по районам

> Дашборд: «как изменяются цены во времени».

```sql
CREATE MATERIALIZED VIEW mv_prices_timeseries_daily
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(day)
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
PARTITION BY toYYYYMMDD(day)
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

### 4. `mv_sentiment_by_district_daily` — тональность сообщений по районам

> Дашборд: «настроение вокруг района» — где жители/СМИ пишут позитивно, где негативно. Контекст для покупки жилья.

```sql
CREATE MATERIALIZED VIEW mv_sentiment_by_district_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (district_slug, day)
AS
SELECT
    toDate(event_time)                AS day,
    arrayJoin(entities_districts)     AS district_slug,
    count()                           AS messages_total,
    countIf(sentiment_label = 'positive') AS pos_count,
    countIf(sentiment_label = 'neutral')  AS neu_count,
    countIf(sentiment_label = 'negative') AS neg_count,
    avg(sentiment_score)              AS sentiment_avg
FROM events_messages
WHERE is_ad = 0 AND length(entities_districts) > 0
GROUP BY day, district_slug;
```

### 5. `mv_topic_cooccurrence_daily` — совместная встречаемость тем

> Дашборд «связи тем»: какие темы часто всплывают в одном сообщении (например, «Бадаевский комплекс» + «ипотечные ставки»). Подсказывает, какие сюжеты идут «парой».

```sql
CREATE MATERIALIZED VIEW mv_topic_cooccurrence_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (topic_a, topic_b, day)
AS
SELECT
    toDate(event_time)              AS day,
    arrayJoin(topics_all)           AS topic_a,
    arrayJoin(topics_all)           AS topic_b,
    count()                         AS cooccurrence_count
FROM events_messages
WHERE is_ad = 0 AND topic_a < topic_b
GROUP BY day, topic_a, topic_b;
```

> Условие `topic_a < topic_b` отсекает дубли симметричных пар и self-pairs.

### 6. `mv_price_distribution_by_rooms_monthly` — распределение цен по комнатности

> Дашборд: «коробчатая диаграмма цены за м² по 1/2/3-комнатным квартирам помесячно». Медиана и перцентили.

```sql
CREATE MATERIALIZED VIEW mv_price_distribution_by_rooms_monthly
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(month)
ORDER BY (city, rooms, month)
AS
SELECT
    toStartOfMonth(event_time)                       AS month,
    city,
    rooms,
    quantilesState(0.25, 0.5, 0.75, 0.9)(price_real / area) AS price_per_m2_quantiles_state,
    countState()                                     AS listings_state
FROM events_prices
WHERE area > 0 AND rooms BETWEEN 0 AND 10
GROUP BY month, city, rooms;
```

> Чтение: `quantilesMerge(0.25, 0.5, 0.75, 0.9)(price_per_m2_quantiles_state)`.

### 7. `mv_model_quality_daily` — качество модели оценки по дням

> Дашборд: «как меняется средний |deviation_pct| модели во времени» — индикатор того, что рынок «уплыл» и пора переобучить.
>
> Это **бизнес-метрика рынка** (поведение модели в реальных рыночных условиях), а не служебная — потому остаётся здесь.

```sql
CREATE MATERIALIZED VIEW mv_model_quality_daily
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (model_version, day)
AS
SELECT
    toDate(event_time)                  AS day,
    model_version,
    countState()                        AS predictions_state,
    avgState(abs(deviation_pct))        AS mae_pct_state,
    quantilesState(0.5, 0.9)(abs(deviation_pct)) AS abs_dev_quantiles_state,
    sumState(toUInt64(is_undervalued))  AS undervalued_state
FROM events_prices
GROUP BY day, model_version;
```

### 8. `mv_listings_by_channel_daily` — поток новых объектов по площадкам

> Дашборд: «сколько новых объектов в день приносит cian.ru vs avito.ru vs domclick.ru, в разрезе типа недвижимости». Бизнес-картина: где живёт предложение.

```sql
CREATE MATERIALIZED VIEW mv_listings_by_channel_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (channel_site, object_kind, day)
AS
SELECT
    toDate(event_time)            AS day,
    channel_site,
    object_kind,
    count()                       AS listings_new,
    avgIf(price_real / area, area > 0) AS avg_price_per_m2,
    sumIf(1, is_undervalued = 1)  AS undervalued_count
FROM events_prices
GROUP BY day, channel_site, object_kind;
```

### 9. `mv_top_undervalued_weekly` — топ недооценённых за период

Считается «на лету» в самом сервисе `metrics` поверх `events_prices` (нет смысла материализовать — выборка маленькая, ad-hoc запрос).

---

## Dictionaries (справочники)

Топики и районы в Postgres-таблицы вынесены **не были** (см. [postgres.md](postgres.md)).

- **`topics`** — справочник лейблов классификатора живёт в артефакте модели в MinIO (`models/nlp/classifier/<version>/labels.json`). Сервис `metrics` отдаёт текущий снимок через HTTP-эндпоинт.
- **`districts`** — берутся из адресов объектов в Mongo (`objects.listing.address`), канонизация — на стороне geocode/normalization-модуля.
- **`sources`** — это единственный «настоящий» справочник в Postgres (`core.sources`).

ClickHouse-словари подключаем только при реальной необходимости джойнить slug → display_name в SQL. Источник для всех — HTTP-эндпоинты сервиса `metrics`, чтобы ClickHouse не зависел напрямую от Postgres/MinIO.

```sql
CREATE DICTIONARY dict_sources
(
    id           UUID,
    kind         String,
    display_name String
)
PRIMARY KEY id
SOURCE(HTTP(url 'http://metrics:8000/internal/dict/sources' format 'JSONEachRow'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED());
```

При необходимости `dict_topics` (из MinIO) и `dict_districts` (из Mongo-агрегации) реализуются по тому же паттерну — через HTTP-эндпоинт в `metrics`.

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
SELECT object_id, district_slug, price_real, deviation_pct
FROM events_prices
WHERE event_time >= now() - INTERVAL 7 DAY
  AND is_undervalued = 1
ORDER BY deviation_pct ASC
LIMIT 10;
```

---

## Что НЕ хранится в ClickHouse

- **Тексты сообщений и сами объекты** → MongoDB.
- **Конфиги, пользователи, активная модель** → PostgreSQL.
- **Бинарники моделей** → MinIO.
- **Служебные метрики системы** (latency API, длительность задач парсинга, размер очередей RabbitMQ, ошибки сервисов) → **observability-стек** (заведём отдельно). Сейчас не хранятся нигде, кроме логов сервисов.
- **Действия пользователей в UI** (клики, просмотры, поисковые запросы) → пока не собираются. Если понадобятся — отдельный поток в observability, не сюда.

## Открытые вопросы

(на текущий момент пусто — основные решения по партиционированию, TTL и движку для `events_prices` зафиксированы выше.)
