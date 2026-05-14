# MongoDB — схема документного хранилища

> **Назначение БД:** хранение документов с гетерогенной структурой — сырые сообщения из Telegram/новостей, объявления недвижимости, результаты NLP-аннотации и оценки моделью. Всё, что плохо ложится в реляционную модель.

## Зоны ответственности и симметрия имён

Сырые данные и результаты их обработки моделями разнесены по разным коллекциям. Имена парные, отличаются постфиксом:

| Сырые (что спарсили) | Обогащённые моделью | Постфикс |
|---|---|---|
| `messages` | `annotated_messages` | `*_messages` |
| `objects` | `annotated_objects` | `*_objects` |

**Принцип:** одна сырая запись → ноль или больше «обогащённых» записей (для разных версий моделей). Актуальная помечается `is_active: true`. Это позволяет:

- независимо переразбирать историю под новые модели;
- хранить несколько версий одного результата для сравнения;
- удалять/пересчитывать обогащение без потери исходника.

## Принципы

- `_id` — `ObjectId` (по умолчанию).
- Везде поля `created_at`, `updated_at` (`ISODate`).
- Ссылки на Postgres-сущности — через **внешний ID** (`source_id: UUID-string`, `model_run_id: UUID-string`). Ссылочной целостности нет, договариваемся на уровне приложения.
- Идемпотентность парсинга — уникальный составной ключ `(source_id, external_id)`.
- TTL для коллекций — **не используем** (история нужна для дашбордов и воспроизводимости).
- Индексы — только под реальные запросы UI и агрегаций.

---

## `messages` — сырые сообщения

Сырые сообщения из Telegram-каналов, новостных сайтов, RSS-лент. Один документ = одно сообщение/статья.

```jsonc
{
  "_id": ObjectId(),
  "source_id": "uuid-source-from-postgres",
  "channel_kind": "tg",               // 'tg' | 'news' | 'rss' | 'html'
  "channel_site": "t.me",             // домен/идентификатор площадки (для news: 'rbc.ru', 'kommersant.ru' и т.п.)
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

**Поля типа источника:**
- `channel_kind` — категория канала: `tg` (Telegram), `news` (новостной сайт), `rss` (RSS-лента), `html` (произвольный HTML-парсинг). Дублирует `core.sources.kind` из Postgres для фильтров без джойна.
- `channel_site` — конкретная площадка (`t.me`, `rbc.ru`, `kommersant.ru`). Нужно для разрезов «по изданию» в дашбордах и для отладки парсера.

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{source_id: 1, external_id: 1}` (unique) | идемпотентность парсинга |
| `{published_at: -1}` | лента «по времени» |
| `{channel_kind: 1, published_at: -1}` | фильтр по типу источника |
| `{channel_site: 1, published_at: -1}` | фильтр по площадке |

---

## `annotated_messages` — результаты NLP для сообщения

Результаты NLP-пайплайна для сообщения. Отдельная коллекция (а не вложенный объект в `messages`) — см. принцип симметрии выше.

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

## `objects` — сырые объекты недвижимости

Объявления о недвижимости в исходном (нормализованном) виде, **без** результатов модели. Один документ = одно объявление, как его увидел парсер.

```jsonc
{
  "_id": ObjectId(),
  "source_id":   "uuid-source",
  "object_kind": "residential",        // 'residential' | 'commercial' | 'land' | 'parking'
  "channel_site": "cian.ru",           // конкретная площадка ('cian.ru', 'avito.ru', 'domclick.ru', ...)
  "external_id": "cian:listing:12345",
  "url":         "https://...",
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

  "status": "active",                  // 'active' | 'sold' | 'removed'
  "history": [                          // история изменения цены
    {"observed_at": ISODate(), "price": 15_000_000},
    {"observed_at": ISODate(), "price": 14_500_000}
  ],

  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

**Поля типа источника:**
- `object_kind` — категория недвижимости: `residential` (жилая), `commercial` (коммерческая), `land` (участки), `parking` (машиноместа). Жёстко влияет на применимую модель оценки (для коммерции — отдельный пайплайн в перспективе).
- `channel_site` — площадка-источник (`cian.ru`, `avito.ru`, `domclick.ru`). Аналог `channel_site` для сообщений — нужно для разрезов «по площадке» и отладки парсеров.

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{source_id: 1, external_id: 1}` (unique) | идемпотентность парсинга |
| `{object_kind: 1, status: 1, published_at: -1}` | лента по типу недвижимости |
| `{channel_site: 1, published_at: -1}` | фильтр по площадке |
| `{listing.address.district_slug: 1, status: 1}` | фильтр по району |
| `{published_at: -1}` | сортировка по свежести |
| `{listing.address.lat: 1, listing.address.lon: 1}` (2dsphere) | гео-запросы / карта |

---

## `annotated_objects` — результаты модели оценки для объекта

Результаты прогона объявления через модель CatBoost (предсказанная цена, отклонение, ранг). Отдельная коллекция по тем же причинам, что и `annotated_messages`:

- независимо переоценивать объекты под новые версии модели;
- хранить несколько версий оценки одного объекта для сравнения / A-B;
- удалять старые оценки без потери исходного объявления.

```jsonc
{
  "_id": ObjectId(),
  "object_id":     ObjectId("..."),    // ссылка на objects._id
  "model_run_id":  "uuid-from-postgres",
  "model_version": "v1.0",             // версия модели (дублирует core.model_registry для удобства)
  "module":        "realestate",       // на случай нескольких модулей оценки

  "predicted_price":  16_200_000,
  "deviation_abs":    -1_700_000,      // listing.price - predicted_price (отрицательное = недооценка)
  "deviation_pct":    -10.49,
  "is_undervalued":   true,
  "rank_in_run":      3,               // место в ранжированном списке этого запуска

  "features_used":    {                // для воспроизводимости и отладки
    "area": 52.4,
    "rooms": 2,
    "district_slug": "presnenskiy",
    /* ... остальные фичи, поданные в модель */
  },

  "is_active":  true,                  // актуальная оценка для object_id
  "computed_at": ISODate(),
  "created_at": ISODate(),
  "updated_at": ISODate()
}
```

**Индексы:**

| Индекс | Назначение |
|---|---|
| `{object_id: 1, is_active: 1}` | получить актуальную оценку для объекта |
| `{is_active: 1, is_undervalued: 1, deviation_pct: 1}` | топ недооценённых |
| `{model_run_id: 1}` | трассируемость запуска |
| `{model_version: 1, is_active: 1}` | срез «всё, что оценено версией v1.0» |
| `{rank_in_run: 1, model_run_id: 1}` | топ-N конкретного запуска |

---

## Связи между коллекциями (текстом)

```
messages._id  ←──  annotated_messages.message_id
objects._id   ←──  annotated_objects.object_id

sources.id (Postgres) ──→ messages.source_id, objects.source_id
model_registry.id (Postgres) ──→ annotated_messages.model_run_id
                                  annotated_objects.model_run_id

topics: метки приходят из артефакта классификатора в MinIO
       (models/nlp/classifier/<version>/labels.json)
       — записываются в annotated_messages.topics[].slug

districts: канонизация при нормализации адреса в realestate-сервисе
           — попадает в objects.listing.address.district_slug
             и annotated_messages.entities[].district_slug
```

## Открытые вопросы

(закрыто — основные решения зафиксированы выше: вложения хранятся как URL без скачивания, `history` достаточно для версионности цены, тренды считаются в ClickHouse из агрегатов, `features_used` в `annotated_objects` хранится целиком.)
