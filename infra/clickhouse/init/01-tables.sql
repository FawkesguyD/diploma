-- =====================================================================
-- Bootstrap-DDL ClickHouse: raw-таблицы + materialized views.
-- Источник: docs/design/databases/clickhouse.md.
-- Запускается один раз при пустом volume CH через /docker-entrypoint-initdb.d.
-- =====================================================================

-- Создаём целевую БД (env CLICKHOUSE_DB не применяется к init-скриптам в .sql,
-- поэтому объявляем явно). Все DDL ниже квалифицируем через USE.
CREATE DATABASE IF NOT EXISTS diploma;
USE diploma;

-- ----- raw: events_messages -----
CREATE TABLE IF NOT EXISTS events_messages
(
    event_time           DateTime64(3) CODEC(Delta, ZSTD),
    published_at         DateTime64(3),

    message_id           String,
    source_id            UUID,
    channel_kind         LowCardinality(String),
    channel_site         LowCardinality(String),

    topic_slug           LowCardinality(String),
    topic_score          Float32,
    topics_all           Array(LowCardinality(String)),

    sentiment_label      LowCardinality(String),
    sentiment_score      Float32,

    is_ad                UInt8,
    lang                 LowCardinality(String),

    entities_districts   Array(LowCardinality(String)),
    entities_developers  Array(String),

    model_run_id         UUID
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (channel_kind, topic_slug, event_time)
TTL toDateTime(event_time) + INTERVAL 24 MONTH;

-- ----- raw: events_prices -----
CREATE TABLE IF NOT EXISTS events_prices
(
    event_time       DateTime64(3) CODEC(Delta, ZSTD),
    published_at     DateTime64(3),

    object_id        String,
    source_id        UUID,
    object_kind      LowCardinality(String),
    channel_site     LowCardinality(String),
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
TTL toDateTime(event_time) + INTERVAL 36 MONTH;

-- =====================================================================
-- Materialized Views (8 шт; mv_top_undervalued_weekly считается ad-hoc)
-- =====================================================================

-- 1. mv_messages_by_topic_hourly
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_messages_by_topic_hourly
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(hour)
ORDER BY (topic_slug, channel_kind, hour)
AS
SELECT
    toStartOfHour(event_time)               AS hour,
    topic_slug,
    channel_kind,
    count()                                  AS messages_total,
    sumIf(1, is_ad = 0)                      AS messages_non_ad,
    avg(sentiment_score)                     AS sentiment_avg,
    countIf(sentiment_label = 'positive')    AS pos_count,
    countIf(sentiment_label = 'negative')    AS neg_count
FROM events_messages
GROUP BY hour, topic_slug, channel_kind;

-- 2. mv_prices_timeseries_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_prices_timeseries_daily
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (city, district_slug, day)
AS
SELECT
    toDate(event_time)                       AS day,
    city,
    district_slug,
    avgState(price_real / area)              AS avg_price_per_m2_state,
    medianState(price_real / area)           AS median_price_per_m2_state,
    avgState(deviation_pct)                  AS avg_deviation_pct_state,
    countState()                             AS listings_seen_state
FROM events_prices
WHERE area > 0
GROUP BY day, city, district_slug;

-- 3. mv_district_activity_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_activity_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (city, district_slug, day)
AS
SELECT
    toDate(event_time)                       AS day,
    city,
    district_slug,
    count()                                  AS listings_new,
    sumIf(1, is_undervalued = 1)             AS undervalued_count,
    avgIf(deviation_pct, is_undervalued = 1) AS avg_undervaluation_pct
FROM events_prices
GROUP BY day, city, district_slug;

-- 4. mv_sentiment_by_district_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_sentiment_by_district_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (district_slug, day)
AS
SELECT
    toDate(event_time)                       AS day,
    arrayJoin(entities_districts)            AS district_slug,
    count()                                  AS messages_total,
    countIf(sentiment_label = 'positive')    AS pos_count,
    countIf(sentiment_label = 'neutral')     AS neu_count,
    countIf(sentiment_label = 'negative')    AS neg_count,
    avg(sentiment_score)                     AS sentiment_avg
FROM events_messages
WHERE is_ad = 0 AND length(entities_districts) > 0
GROUP BY day, district_slug;

-- 5. mv_topic_cooccurrence_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_topic_cooccurrence_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (topic_a, topic_b, day)
AS
SELECT
    toDate(event_time)                       AS day,
    arrayJoin(topics_all)                    AS topic_a,
    arrayJoin(topics_all)                    AS topic_b,
    count()                                  AS cooccurrence_count
FROM events_messages
WHERE is_ad = 0 AND topic_a < topic_b
GROUP BY day, topic_a, topic_b;

-- 6. mv_price_distribution_by_rooms_monthly
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_price_distribution_by_rooms_monthly
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(month)
ORDER BY (city, rooms, month)
AS
SELECT
    toStartOfMonth(event_time)                                  AS month,
    city,
    rooms,
    quantilesState(0.25, 0.5, 0.75, 0.9)(price_real / area)     AS price_per_m2_quantiles_state,
    countState()                                                AS listings_state
FROM events_prices
WHERE area > 0 AND rooms BETWEEN 0 AND 10
GROUP BY month, city, rooms;

-- 7. mv_model_quality_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_model_quality_daily
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (model_version, day)
AS
SELECT
    toDate(event_time)                                AS day,
    model_version,
    countState()                                      AS predictions_state,
    avgState(abs(deviation_pct))                      AS mae_pct_state,
    quantilesState(0.5, 0.9)(abs(deviation_pct))      AS abs_dev_quantiles_state,
    sumState(toUInt64(is_undervalued))                AS undervalued_state
FROM events_prices
GROUP BY day, model_version;

-- 8. mv_listings_by_channel_daily
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_listings_by_channel_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(day)
ORDER BY (channel_site, object_kind, day)
AS
SELECT
    toDate(event_time)                       AS day,
    channel_site,
    object_kind,
    count()                                  AS listings_new,
    avgIf(price_real / area, area > 0)       AS avg_price_per_m2,
    sumIf(1, is_undervalued = 1)             AS undervalued_count
FROM events_prices
GROUP BY day, channel_site, object_kind;
