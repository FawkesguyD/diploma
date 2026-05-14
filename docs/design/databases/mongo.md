# MongoDB — схема документного хранилища

> **Назначение БД:** хранение документов с гетерогенной структурой — сырые сообщения из Telegram/новостей, объявления недвижимости, результаты NLP-аннотации. Всё, что плохо ложится в реляционную модель.

## Зоны ответственности

1. **`messages`** — сырые сообщения и новости (нормализованные).
2. **`nlp_annotations`** — результаты NLP-обработки сообщений (классификация, NER, тональность, метки рекламы).
3. **`realestate_listings`** — объявления о недвижимости + результаты модели (предсказанная цена, отклонение, ранг).
4. **`raw_payloads`** _(опц.)_ — сырые дампы ответов сторонних API/HTML на случай переразбора.

## Принципы

- `_id` — `ObjectId` (по умолчанию).
- Везде поля `created_at`, `updated_at` (`ISODate`).
- Ссылки на Postgres-сущности — через **внешний ID** (`source_id: UUID-string`, `model_run_id: UUID-string`). Ссылочной целостности нет, договариваемся на уровне приложения.
- Идемпотентность парсинга — уникальный составной ключ `(source_id, external_id)`.
- TTL для коллекций — **не используем** (история нужна для дашбордов и воспроизводимости).
- Индексы — только под реальные запросы UI и агрегаций.

---

## `messages`

Сырые сообщения из Telegram-каналов и новостей. Один документ = одно сообщение/статья.

```jsonc
{
  "_id": ObjectId(),
  "source_id": "uuid-source-from-postgres",
  "source_kind": "telegram",          // дублируем для удобных фильтров без джойна
  "external_id": "channel:12345:678", // уникальный ID в источнике (telegram msg_id, news guid)
  "url": "https://t.me/channel/678",  // null для приватных
  "author": {
    "name": "ChannelName",
    "handle": "@channel",
    "avatar_url": null
  },
  "published_at": ISODate("2026-05-14T10:00:00Z"),
  "fetched_at":   ISODate("2026-05-14T10:00:42Z"),

  "text": "...",                      // полный текст
  "lang": "ru",                       // определяется при нормализации

  "media": [                           // вложения
    {
      "type": "image",
      "url": "https://.../photo.jpg",
      "caption": null
    }
  ],

  "raw_meta": {                        // оригинальные метаданные источника
    "views": 12345,
    "forwards": 12,
    "reply_to_id": null
  },

  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{source_id: 1, external_id: 1}` (unique) | идемпотентность парсинга |
| `{published_at: -1}` | лента «по времени» |
| `{source_kind: 1, published_at: -1}` | фильтр по типу источника |

---

## `nlp_annotations`

Результаты NLP-пайплайна для сообщения. **Отдельная коллекция** (а не вложенный объект в `messages`), чтобы:

- независимо переразбирать историю под новые модели;
- хранить несколько версий аннотации одного сообщения (одна актуальная + старые для сравнения).

```jsonc
{
  "_id": ObjectId(),
  "message_id": ObjectId("..."),       // ссылка на messages._id
  "model_run_id": "uuid-from-postgres",// какой запуск это сделал
  "models": {                          // какие модели и версии использовались
    "classifier": "v0.2",
    "ner":        "v0.1",
    "sentiment":  "v0.1",
    "ad_filter":  "v0.1"
  },

  "is_ad": false,
  "ad_score": 0.07,

  "topics": [                          // классификатор тематик
    {"slug": "badaevsky_complex", "score": 0.91},
    {"slug": "mortgage_rates",    "score": 0.12}
  ],

  "sentiment": {
    "label": "neutral",                // 'positive' | 'neutral' | 'negative'
    "score": 0.62
  },

  "entities": [                        // NER
    {"type": "location",  "text": "Бадаевский пивзавод", "district_slug": "presnenskiy"},
    {"type": "developer", "text": "Capital Group"},
    {"type": "money",     "text": "350 тыс ₽/м²", "value": 350000, "unit": "rub_per_m2"}
  ],

  "summary": "Краткое описание (опц., если используем суммаризатор).",

  "is_active": true,                   // актуальная аннотация для message_id
  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{message_id: 1, is_active: 1}` | получить актуальную аннотацию для сообщения |
| `{topics.slug: 1, is_active: 1}` | фильтр ленты по теме |
| `{is_ad: 1, is_active: 1}` | скрыть рекламу в ленте |
| `{sentiment.label: 1, is_active: 1}` | фильтр по тональности |
| `{entities.district_slug: 1}` | сообщения по району |
| `{model_run_id: 1}` | трассируемость запуска |

---

## `realestate_listings`

Объявления о недвижимости + результаты модели оценки.

```jsonc
{
  "_id": ObjectId(),
  "source_id": "uuid-source",
  "external_id": "cian:listing:12345",
  "url": "https://...",
  "fetched_at":  ISODate(),
  "published_at": ISODate(),

  "listing": {                         // нормализованные параметры
    "price":     14_500_000,           // ₽
    "currency":  "RUB",
    "area":      52.4,                 // м²
    "rooms":     2,
    "floor":     7,
    "total_floors": 16,
    "year_built": 2008,
    "address": {
      "raw": "Москва, ул. ...",
      "city": "Moscow",
      "district_slug": "presnenskiy",
      "lat": 55.760,
      "lon": 37.580
    },
    "features": ["balcony", "renovation_eu"],
    "raw_extra": { /* специфичные поля сайта */ }
  },

  "prediction": {                      // результат модели (может отсутствовать)
    "model_run_id": "uuid",
    "model_version": "v1.0",
    "predicted_price": 16_200_000,
    "deviation_abs": -1_700_000,       // listing.price - predicted
    "deviation_pct": -10.49,
    "is_undervalued": true,
    "rank_in_run": 3,                  // место в ранжированном списке этого запуска
    "computed_at": ISODate()
  },

  "status": "active",                  // 'active' | 'sold' | 'removed'
  "history": [                          // история изменения цены
    {"observed_at": ISODate(), "price": 15_000_000},
    {"observed_at": ISODate(), "price": 14_500_000}
  ],

  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{source_id: 1, external_id: 1}` (unique) | идемпотентность парсинга |
| `{prediction.is_undervalued: 1, prediction.deviation_pct: 1}` | топ недооценённых |
| `{listing.address.district_slug: 1, status: 1}` | фильтр по району |
| `{published_at: -1}` | сортировка по свежести |
| `{listing.address.lat: 1, listing.address.lon: 1}` (2dsphere) | гео-запросы / карта |

---

## `raw_payloads` (опционально)

Сырые ответы (HTML/JSON) на случай переразбора. Можно отключить, если жалко места.

```jsonc
{
  "_id": ObjectId(),
  "source_id": "uuid",
  "external_id": "...",
  "fetched_at": ISODate(),
  "content_type": "text/html",
  "payload": "...",                    // строка или GridFS-ссылка
  "checksum_sha256": "..."
}
```

**Индексы:** `{source_id: 1, external_id: 1, fetched_at: -1}`.

---

## Связи между коллекциями (текстом)

```
messages._id  ←──  nlp_annotations.message_id
sources.id (Postgres) ──→ messages.source_id, realestate_listings.source_id
model_registry.id (Postgres) ──→ realestate_listings.prediction.model_run_id
                                  nlp_annotations.model_run_id
topics.slug (Postgres) ──→ nlp_annotations.topics[].slug
districts.slug (Postgres) ──→ realestate_listings.listing.address.district_slug,
                              nlp_annotations.entities[].district_slug
```

## Открытые вопросы

- [ ] Хранить ли вложения (изображения) в GridFS или только URL? Предлагаю — URL, без скачивания (экономия места, проще приватность).
- [ ] Нужна ли версионность объявлений (snapshot при каждом изменении) или достаточно поля `history` с ценой? По плану дашбордов — достаточно `history`.
- [ ] Нужна ли отдельная коллекция `trends` для извлечённых трендов, или это лучше пересчитывать в ClickHouse из агрегатов? Предлагаю — в ClickHouse (см. `clickhouse.md`).
