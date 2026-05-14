# REST API — контракт фронт ↔ шлюз

> Эта папка фиксирует, как фронтенд общается со шлюзом. Шлюз (Traefik / Nginx) маршрутизирует запросы на бэкенд-сервисы по префиксу пути; для фронта вся система выглядит как одно API.
>
> Источник правды — `openapi.yaml`. Этот README — навигация и принципы; конкретные пути / схемы тел смотреть в OpenAPI.

## Маршрутизация в шлюзе

| Префикс | Сервис | Назначение |
|---|---|---|
| `/api/auth/*`            | nlp-parser (auth-модуль)   | логин, текущий пользователь |
| `/api/sources/*`         | nlp-parser                 | управление источниками |
| `/api/messages/*`        | nlp-parser                 | лента сообщений + аннотации |
| `/api/objects/*`         | realestate                 | объекты недвижимости + оценки |
| `/api/model-runs/*`      | realestate / nlp-parser    | запуски моделей, ранжирования |
| `/api/jobs/*`            | соответствующий сервис     | статусы фоновых задач (парсинг и т.п.) |
| `/api/subscriptions/*`   | nlp-parser                 | подписки пользователя |
| `/api/dashboards/*`      | metrics                    | данные для дашбордов рынка |
| `/*`                     | frontend (статика)         | SPA |

Сам бэкенд сервис auth-эндпоинты держит в nlp-parser **на этапе диплома** ради простоты. Если позже понадобится — выделим отдельный auth-сервис, маршрутизация на стороне шлюза не меняется.

## Принципы

- **JSON везде.** UTF-8, `application/json`.
- **Время** — ISO-8601 в UTC.
- **Пагинация** — cursor-based (`?cursor=...&limit=50`) для лент и списков с длинной историей; offset-пагинация (`?page=1&page_size=20`) — для коротких справочников. В ответе всегда `next_cursor` или `total`.
- **Сортировка** — `?sort=published_at:desc` (поле:направление).
- **Фильтры** — простые query-параметры (`?topic=badaevsky_complex&since=2026-05-01`). Сложные фильтры (по нескольким условиям с OR) — POST с телом, если понадобятся; пока не предполагаем.
- **Идентификаторы** — UUID для Postgres-сущностей, hex `_id` Mongo для документов. В URL — как есть.
- **Аутентификация** — `Authorization: Bearer <JWT>` для всех `/api/*`, кроме `POST /api/auth/login`. JWT stateless ([ADR-0008](../../decisions/0008-postgres-core-ops-schemas.md) — `auth_sessions` исключена).
- **Ошибки** — формат RFC 7807 (Problem Details for HTTP APIs):

```json
{
  "type": "/errors/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "Field 'limit' must be <= 1000",
  "instance": "/api/messages?limit=999999"
}
```

- **Долгие операции** — `202 Accepted` + `{job_id, status_url}`. Клиент поллит `GET /api/jobs/{id}` или подписывается на SSE (см. ниже).
- **Server-Sent Events** для «живой» ленты сообщений (`GET /api/messages/stream` с `Accept: text/event-stream`). WebSocket не используем — для one-way push SSE проще, прокси-friendly.
- **Версионирование** — пока без префикса версии (`/api/...`, а не `/api/v1/...`). Это **дипломный проект, нет внешних клиентов**. Если появится обратная совместимость как требование — введём `/api/v2/...` параллельно.

## Группы эндпоинтов (high-level)

### `/api/auth`

- `POST /login` — `{email, password}` → `{token, user}`. Stateless JWT, TTL ≈ 30 мин.
- `GET /me` — текущий пользователь.

### `/api/sources`

CRUD над `core.sources`. Только для `role='admin'`.

- `GET /sources` — список с фильтрами по `kind`, `enabled`.
- `POST /sources` — создать.
- `PATCH /sources/{id}` — обновить (включить/выключить, поменять interval).
- `DELETE /sources/{id}` — soft delete.
- `POST /sources/{id}/parse` — запустить парсинг прямо сейчас → `202 + {job_id}`.

### `/api/messages`

Лента сообщений + аннотации. Только чтение (записи кладёт парсер).

- `GET /messages` — параметры: `topic`, `district`, `sentiment`, `channel_kind`, `channel_site`, `source_id`, `since`, `until`, `is_ad`, `cursor`, `limit`. Возвращает denormalized: сообщение + актуальная аннотация одним объектом.
- `GET /messages/{id}` — детальный просмотр.
- `GET /messages/stream` — SSE-поток новых сообщений (фильтры в query так же, как у `GET /messages`).

### `/api/objects`

Объекты недвижимости + оценка модели.

- `GET /objects` — параметры: `object_kind`, `channel_site`, `district`, `city`, `rooms`, `price_min`, `price_max`, `area_min`, `area_max`, `is_undervalued`, `status`, `sort`, `cursor`, `limit`.
- `GET /objects/{id}` — детальный просмотр + актуальная `annotated_objects`.
- `GET /objects/{id}/history` — история цены.
- `GET /objects/top-undervalued` — топ недооценённых (с фильтрами по району/городу/типу).

### `/api/model-runs`

Журнал запусков моделей (read-only, из `ops.model_runs`).

- `GET /model-runs` — список, фильтры по `module`, `status`, `since`.
- `GET /model-runs/{id}` — детали + список оценённых объектов.
- `POST /model-runs` — запустить новый run вручную (admin) → `202 + {job_id}`.

### `/api/jobs`

Статусы фоновых задач (парсинг, инференс) — единый эндпоинт для разных типов.

- `GET /jobs/{id}` — `{id, kind, status, started_at, finished_at, progress, result?, error?}`. Сервис, обслуживающий эндпоинт, определяется префиксом `job_id` или через `kind` в URL: `/api/jobs/parser/{id}`, `/api/jobs/model-runs/{id}` — решим в реализации.

### `/api/subscriptions`

Пользовательские «избранные» (`core.user_subscriptions`).

- `GET /subscriptions` — список своих подписок.
- `POST /subscriptions` — `{target_kind, target_ref, notify?}`.
- `DELETE /subscriptions/{id}`.

### `/api/dashboards`

Готовые срезы для UI-дашбордов. Не «голый ClickHouse SQL», а семантические эндпоинты.

- `GET /dashboards/topics/activity?topic=...&since=...&until=...&granularity=hour` — временной ряд для виджета «активность по теме».
- `GET /dashboards/prices/timeseries?city=...&district=...&granularity=month` — динамика средней цены за м².
- `GET /dashboards/districts/activity?city=...&since=...` — карта/таблица активности по районам.
- `GET /dashboards/objects/top-undervalued?since=...&limit=10` — топ для главной страницы.
- `GET /dashboards/sentiment/by-district?since=...` — тональность по районам.
- `GET /dashboards/model-quality?model_version=...&since=...` — поведение модели во времени.

Каждый эндпоинт — это один MV в ClickHouse + лёгкое преобразование для фронта.

## Структура `openapi.yaml`

`openapi.yaml` сгенерируется автоматически из FastAPI (`/openapi.json` каждого сервиса) + объединится скриптом в один файл. На этапе проектирования держим ручной черновик-сводку (см. файл `openapi.yaml` рядом).

## Решения по реализации

- **Без отдельного `/api/admin/*` префикса.** Проверка роли (`require_role("admin")`) — декоратор/dependency внутри обычных ручек `/api/*`. Причины: (1) одна и та же сущность нередко доступна и юзеру (read), и админу (write) — разделять префиксы значит дублировать роутинг; (2) шлюзу не нужно знать про роли — JWT валидируется в сервисе, шлюз только маршрутизирует; (3) ошибочно «забыть префикс» сложнее, чем «забыть декоратор» — декоратор тестируется юнит-тестом, префикс — нет. Минус: нельзя одним правилом в шлюзе закрыть «всё админское» от внешнего трафика — но для одного хоста это не проблема.

- **CORS — whitelist одного origin из `.env`.** Переменная `FRONTEND_ORIGIN` (например, `http://localhost:5173` локально, `https://diploma.local` в проде). Настройка на уровне шлюза (Traefik middleware `headers.accessControlAllowOriginList`), а не в каждом сервисе — единая точка контроля. Если позже появится мобильное приложение или внешние интеграции — пересмотрим (вероятно, на JWT-валидацию без CORS, т.к. это будут не-браузерные клиенты).
