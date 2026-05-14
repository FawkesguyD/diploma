# PostgreSQL — схема основной БД

> **Назначение БД:** реляционные данные с транзакциями и ссылочной целостностью. **НЕ** для сырых сообщений и метрик.

## Структура: две схемы

Таблицы разделены на две схемы PostgreSQL — см. [ADR-0008](../../decisions/0008-postgres-core-ops-schemas.md):

| Схема | Назначение | Таблицы |
|---|---|---|
| **`core`** | состояние системы (что ЕСТЬ и как настроено) | `users`, `sources`, `model_registry`, `module_configs` |
| **`ops`** | журнал событий (что ПРОИСХОДИТ) | `parser_jobs`, `model_runs` |

FK между схемами разрешены: `ops.* → core.*`.

## Принципы

- Primary keys — `uuid` (gen_random_uuid()).
- Везде `created_at` / `updated_at` (timestamptz).
- `soft_delete` через `deleted_at IS NULL` (не удаляем источники / запуски, чтобы сохранить историю).
- Миграции через Alembic (база — [model/alembic](/Users/daniel/Projects/ДИПЛОМ/model/alembic)).
- Первая миграция создаёт обе схемы: `CREATE SCHEMA IF NOT EXISTS core; CREATE SCHEMA IF NOT EXISTS ops;`.
- В SQLAlchemy-моделях схема задаётся через `__table_args__ = {"schema": "core"}` / `"ops"`.
- JSON-поля (`jsonb`) — для гибкой конфигурации модулей, чтобы не плодить колонки.

---

## Схема `core` — состояние системы

### `core.users` — пользователи системы

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `email` | text UNIQUE NOT NULL | логин |
| `password_hash` | text NOT NULL | bcrypt/argon2 |
| `display_name` | text | |
| `role` | text NOT NULL DEFAULT `'user'` | `'user' \| 'admin'` |
| `is_active` | bool NOT NULL DEFAULT true | |
| `created_at` | timestamptz NOT NULL | |
| `updated_at` | timestamptz NOT NULL | |

**Индексы:** unique(`email`).

### `core.sources` — источники информационных потоков

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `kind` | text NOT NULL | `'telegram' \| 'rss' \| 'html' \| 'realestate_site'` |
| `name` | text NOT NULL | человекочитаемое имя |
| `url_or_handle` | text NOT NULL | `@channel`, RSS URL, домен сайта |
| `enabled` | bool NOT NULL DEFAULT true | |
| `poll_interval_sec` | int NOT NULL DEFAULT 300 | как часто опрашивать |
| `config` | jsonb NOT NULL DEFAULT `'{}'` | специфичные параметры (cookies, селекторы, фильтры) |
| `last_polled_at` | timestamptz | |
| `created_at` | timestamptz NOT NULL | |
| `updated_at` | timestamptz NOT NULL | |
| `deleted_at` | timestamptz | soft delete |

**Индексы:** (`kind`, `enabled`), (`last_polled_at`).

### `core.model_registry` — реестр моделей в MinIO

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `task` | text NOT NULL | `'realestate_price' \| 'nlp_classifier' \| 'ner' \| 'sentiment' \| 'ad_filter'` |
| `version` | text NOT NULL | `'v1.0'`, `'v1.1'` и т.п. |
| `minio_path` | text NOT NULL | `models/<task>/<version>/...` |
| `metadata` | jsonb NOT NULL | фичи, гиперпараметры, метрики на отложке |
| `is_active` | bool NOT NULL DEFAULT false | какая версия используется сейчас |
| `created_at` | timestamptz NOT NULL | |

**Индексы:** unique(`task`, `version`), partial unique on (`task`) where `is_active = true` (одна активная версия на задачу).

### `core.module_configs` — конфигурации аналитических модулей

Гибкая таблица — каждая запись описывает конфиг одного модуля (что использовать, какие пороги).

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `module` | text NOT NULL | `'realestate' \| 'nlp_classifier' \| 'ner' \| 'sentiment' \| 'trend_extractor'` |
| `name` | text NOT NULL | имя конфига (можно держать несколько профилей) |
| `is_active` | bool NOT NULL DEFAULT false | активный профиль для модуля |
| `model_id` | uuid FK → core.model_registry.id | какую модель использовать (если применимо) |
| `params` | jsonb NOT NULL DEFAULT `'{}'` | пороги, batch size, тематики и т.п. |
| `created_at` | timestamptz NOT NULL | |
| `updated_at` | timestamptz NOT NULL | |

**Индексы:** unique(`module`, `name`), partial unique on (`module`) where `is_active = true`.

### `core.user_subscriptions` — пользовательские «избранные»

Подписки пользователя на источники, темы и конкретные объекты недвижимости. Гетерогенная сущность (target — это либо источник, либо тема, либо объект), поэтому одна таблица с дискриминатором `target_kind` + полиморфные `target_id` / `target_slug`.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → core.users.id | владелец подписки |
| `target_kind` | text NOT NULL | `'source' \| 'topic' \| 'object'` |
| `target_id` | uuid | заполнено для `source` (→ `core.sources.id`) и `object` (Mongo ObjectId как UUID-строка не годится → используем `target_ref`) |
| `target_ref` | text | универсальная строковая ссылка: для `topic` — `topic_slug`, для `object` — Mongo `_id` в hex, для `source` — дублирует `target_id::text` |
| `notify` | bool NOT NULL DEFAULT false | присылать ли уведомления (на будущее, пока не используется) |
| `created_at` | timestamptz NOT NULL | |

**Почему `target_ref text`, а не отдельные колонки на каждый тип:** объекты живут в Mongo (`ObjectId`, не UUID), темы — это slug-строка из артефакта модели. Если завести `source_id`/`topic_slug`/`object_id` отдельными колонками с FK только на `core.sources` — таблица читается чище, но три из четырёх колонок всегда `NULL`. Полиморфная пара `(target_kind, target_ref)` компактнее и расширяемее (завтра — `developer`, `district` без миграции схемы). Целостность для `source` поддерживается на уровне приложения (проверка существования при создании).

**Индексы:**
- unique(`user_id`, `target_kind`, `target_ref`) — нельзя подписаться на одно и то же дважды.
- (`target_kind`, `target_ref`) — обратный поиск «кто подписан на эту тему».

---



### `ops.parser_jobs` — журнал запусков парсера

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `source_id` | uuid FK → core.sources.id | |
| `status` | text NOT NULL | `'pending' \| 'running' \| 'succeeded' \| 'failed'` |
| `started_at` | timestamptz | |
| `finished_at` | timestamptz | |
| `items_collected` | int DEFAULT 0 | сколько сообщений/объявлений собрано |
| `error` | text | если упал |
| `metadata` | jsonb DEFAULT `'{}'` | произвольные данные о запуске |

**Индексы:** (`source_id`, `started_at` DESC), (`status`).

### `ops.model_runs` — журнал инференса/ранжирования

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `module` | text NOT NULL | `'realestate' \| 'nlp_classifier' \| ...` |
| `model_id` | uuid FK → core.model_registry.id | |
| `module_config_id` | uuid FK → core.module_configs.id | |
| `triggered_by` | text NOT NULL | `'schedule' \| 'manual' \| 'queue'` |
| `status` | text NOT NULL | как в parser_jobs |
| `started_at` | timestamptz | |
| `finished_at` | timestamptz | |
| `items_processed` | int DEFAULT 0 | |
| `result_ref` | jsonb | ссылки на результаты в Mongo: `{"collection": "realestate_listings", "ids": [...]}` |
| `error` | text | |

**Индексы:** (`module`, `started_at` DESC).

---

## Что было убрано из схемы

### `topics` и `districts` — _(убрано)_

Изначально планировались справочники тематик и районов. Решено отказаться:

- **`topics`** — список тематик жёстко привязан к версии классификатора (v0.1 знает 12 тем, v0.2 — 18). Эти данные путешествуют **вместе с моделью** в MinIO (`models/nlp/classifier/<version>/labels.json`). Сервис NLP при загрузке модели подтягивает справочник в память и отдаёт UI через эндпоинт.
- **`districts`** — извлекаются из адресов объявлений в `realestate_listings.listing.address` (Mongo). Канонизация (slug + display name) выполняется на стороне geocode/normalization-модуля. Если потребуется хранить геополигоны — добавится отдельной миграцией позже.

`topic_slug` и `district_slug` остаются строковыми денормализованными ключами в Mongo и ClickHouse (как было запланировано), но без отдельных Postgres-таблиц для них.

### `auth_sessions` — _(убрано)_

Изначально планировалась таблица для refresh-токенов и отзыва сессий. Решено отказаться: для дипломного проекта используется простой stateless JWT с коротким TTL (≈30 мин) и повторным логином. Если позже понадобится «выйти со всех устройств» — добавится одной миграцией.

---

## ER-сводка (текстом)

```
core.users — без связей с сессиями (stateless JWT)

core.users                1 ─── n  core.user_subscriptions
core.sources              1 ─── n  core.user_subscriptions  (target_kind='source')
core.sources              1 ─── n  ops.parser_jobs
core.model_registry       1 ─── n  core.module_configs
core.model_registry       1 ─── n  ops.model_runs
core.module_configs       1 ─── n  ops.model_runs

(topic_slug и district_slug — строковые денормализованные ключи
 в Mongo и ClickHouse; справочников в Postgres для них нет)
```

## Что НЕ хранится в Postgres

- **Сами сообщения / тексты** → MongoDB.
- **Объявления недвижимости и результаты предсказаний** → MongoDB.
- **NLP-аннотации** → MongoDB.
- **Метрики и агрегаты для дашбордов** → ClickHouse.
- **Бинарники моделей** → MinIO (Postgres хранит только метаданные в `core.model_registry`).

## Открытые вопросы

(закрыто — аудит-лог решено не заводить; подписки пользователей реализованы таблицей `core.user_subscriptions` выше.)
