# PostgreSQL — схема основной БД

> **Назначение БД:** реляционные данные с транзакциями и ссылочной целостностью — пользователи, настройки, источники данных, метаданные запусков моделей и парсеров. **НЕ** для сырых сообщений и метрик.

## Зоны ответственности

1. **Аутентификация и пользователи** — кто заходит в систему.
2. **Источники данных** — справочник Telegram-каналов, RSS-фидов, сайтов объявлений.
3. **Конфигурации модулей** — какие модели/параметры использовать в каком модуле.
4. **Реестр запусков** — `model_runs`, `parser_jobs` — что и когда запускалось, ссылки на артефакты в MinIO и результаты в MongoDB.
5. **Справочники** для дашбордов: топики/категории/районы (если требуется FK с другими таблицами).

## Принципы

- Primary keys — `uuid` (gen_random_uuid()).
- Везде `created_at` / `updated_at` (timestamptz).
- `soft_delete` через `deleted_at IS NULL` (не удаляем источники / запуски, чтобы сохранить историю).
- Миграции через Alembic (база — [model/alembic](/Users/daniel/Projects/ДИПЛОМ/model/alembic)).
- JSON-поля (`jsonb`) — для гибкой конфигурации модулей, чтобы не плодить колонки.

## Таблицы

### `users` — пользователи системы

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

### `sources` — источники информационных потоков

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

### `parser_jobs` — журнал запусков парсера

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `source_id` | uuid FK → sources.id | |
| `status` | text NOT NULL | `'pending' \| 'running' \| 'succeeded' \| 'failed'` |
| `started_at` | timestamptz | |
| `finished_at` | timestamptz | |
| `items_collected` | int DEFAULT 0 | сколько сообщений/объявлений собрано |
| `error` | text | если упал |
| `metadata` | jsonb DEFAULT `'{}'` | произвольные данные о запуске |

**Индексы:** (`source_id`, `started_at` DESC), (`status`).

### `model_registry` — реестр моделей в MinIO

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

### `module_configs` — конфигурации аналитических модулей

Гибкая таблица — каждая запись описывает конфиг одного модуля (что использовать, какие пороги).

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `module` | text NOT NULL | `'realestate' \| 'nlp_classifier' \| 'ner' \| 'sentiment' \| 'trend_extractor'` |
| `name` | text NOT NULL | имя конфига (можно держать несколько профилей) |
| `is_active` | bool NOT NULL DEFAULT false | активный профиль для модуля |
| `model_id` | uuid FK → model_registry.id | какую модель использовать (если применимо) |
| `params` | jsonb NOT NULL DEFAULT `'{}'` | пороги, batch size, тематики и т.п. |
| `created_at` | timestamptz NOT NULL | |
| `updated_at` | timestamptz NOT NULL | |

**Индексы:** unique(`module`, `name`), partial unique on (`module`) where `is_active = true`.

### `model_runs` — журнал инференса/ранжирования

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `module` | text NOT NULL | `'realestate' \| 'nlp_classifier' \| ...` |
| `model_id` | uuid FK → model_registry.id | |
| `module_config_id` | uuid FK → module_configs.id | |
| `triggered_by` | text NOT NULL | `'schedule' \| 'manual' \| 'queue'` |
| `status` | text NOT NULL | как в parser_jobs |
| `started_at` | timestamptz | |
| `finished_at` | timestamptz | |
| `items_processed` | int DEFAULT 0 | |
| `result_ref` | jsonb | ссылки на результаты в Mongo: `{"collection": "realestate_listings", "ids": [...]}` |
| `error` | text | |

**Индексы:** (`module`, `started_at` DESC).

### `topics` — справочник тематик (для классификатора и дашбордов)

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `slug` | text UNIQUE NOT NULL | `'badaevsky_complex'`, `'mortgage_rates'` |
| `display_name` | text NOT NULL | |
| `description` | text | |
| `parent_id` | uuid FK → topics.id | иерархия (опц.) |

**Индексы:** unique(`slug`).

### `districts` — справочник районов (для realestate и дашбордов)

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `slug` | text UNIQUE NOT NULL | |
| `display_name` | text NOT NULL | |
| `city` | text NOT NULL | |
| `geo` | jsonb | bbox / polygon (опц.) |

### `auth_sessions` — refresh-токены / сессии JWT

Если идём с JWT — таблица для refresh-токенов (revocation list).

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → users.id | |
| `refresh_token_hash` | text NOT NULL | |
| `expires_at` | timestamptz NOT NULL | |
| `revoked_at` | timestamptz | |
| `created_at` | timestamptz NOT NULL | |

## ER-сводка (текстом)

```
users 1 ─── n auth_sessions
sources 1 ─── n parser_jobs
model_registry 1 ─── n module_configs
model_registry 1 ─── n model_runs
module_configs 1 ─── n model_runs
topics — справочник, ссылается из jsonb-полей в module_configs
districts — справочник, ссылается из MongoDB.realestate_listings
```

## Что НЕ хранится в Postgres

- **Сами сообщения / тексты** → MongoDB.
- **Объявления недвижимости и результаты предсказаний** → MongoDB.
- **NLP-аннотации** → MongoDB.
- **Метрики и агрегаты для дашбордов** → ClickHouse.
- **Бинарники моделей** → MinIO (Postgres хранит только метаданные в `model_registry`).

## Открытые вопросы

- [ ] Нужна ли таблица `audit_log` для действий админа (включил/выключил источник, переключил активную модель)? Полезно для диплома (показать аудит).
- [ ] Хранить ли в `topics` дерево или плоский список? Если будут темы и подтемы — нужен `parent_id` и закрытые операции `WITH RECURSIVE`.
- [ ] Хранить ли пользовательские «избранные» источники / темы / объекты? Если да — таблица `user_subscriptions`.
