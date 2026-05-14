# Справочник API endpoints

Основной runtime API находится в [`apps/api/api.py`](../../apps/api/api.py). Совместимый root entrypoint [`api.py`](../../api.py) экспортирует тот же `app`, поэтому работают оба запуска:

```bash
uvicorn api:app
uvicorn apps.api.api:app
```

## Общие правила

- API работает в RUB-only режиме.
- Prediction endpoints загружают active model через readiness manifest.
- Невалидный input в direct prediction возвращает HTTP 400.
- `/opportunities` и `/shortlist` требуют authenticated session.
- UI зависит от flattened opportunity shape, который мапится в [`opportunityMappers.ts`](../../apps/ui/src/features/opportunities/api/opportunityMappers.ts).

## `GET /`

Назначение: service discovery.

Форма ответа:

```json
{
  "service": "real-estate-mvp-api",
  "mode": "proxy-valuation",
  "base_currency": "RUB",
  "currency_mode": "RUB-only",
  "docs_url": "/docs",
  "health_url": "/health",
  "login_url": "/auth/login",
  "current_user_url": "/auth/me",
  "opportunities_url": "/opportunities",
  "shortlist_url": "/shortlist",
  "predict_url": "/predict",
  "batch_predict_url": "/predict/batch"
}
```

Связь с моделью: модель не вызывается.

## `GET /health`

Назначение: readiness API и модели.

Response:

```json
{
  "status": "ok",
  "model_status": "active",
  "base_currency": "RUB"
}
```

Связь с моделью: endpoint загружает bundle через `get_model_bundle()`. Если manifest или active artifact невалидны, health тоже падает.

## `POST /predict`

Назначение: single proxy valuation.

Request:

```json
{
  "object_features": {
    "rooms": 2,
    "area": 50,
    "kitchen_area": 8,
    "level": 3,
    "levels": 9,
    "listing_price": 6500000,
    "listing_currency": "RUB"
  },
  "output_currency": "RUB",
  "fx_rate": null,
  "include_explanation": true
}
```

Response: `PredictionResponse`, см. [model-outputs.md](model-outputs.md).

Важные особенности:

- `output_currency` должен быть ровно `"RUB"` на уровне API schema.
- `fx_rate` валидируется как положительный, но не используется.
- `listing_currency` внутри `object_features` должен быть `RUB` или отсутствовать.
- Полная спецификация полей: [model-inputs.md](model-inputs.md).

Связь с моделью: вызывает `predict_proxy_valuation_from_bundle`.

## `POST /predict/batch`

Назначение: batch scoring и опциональное ранжирование по undervaluation.

Request:

```json
{
  "objects": [
    {
      "listing_id": "1",
      "rooms": 2,
      "area": 50,
      "kitchen_area": 8,
      "level": 3,
      "levels": 9,
      "listing_price": 6500000,
      "listing_currency": "RUB"
    }
  ],
  "rank_by_undervaluation": true,
  "output_currency": "RUB",
  "fx_rate": null,
  "include_explanations": false
}
```

Response:

```json
{
  "count": 1,
  "ranked": true,
  "results": []
}
```

Важные особенности:

- `objects` должен содержать минимум 1 элемент.
- API добавляет `input_index`.
- Один невалидный объект ломает весь batch HTTP 400.
- При ранжировании порядок results может отличаться от входного.

Связь с моделью: вызывает `score_proxy_valuations_from_bundle`.

## `POST /auth/login`

Назначение: создать session cookie для UI.

Request:

```json
{
  "email": "investor@example.com",
  "password": "demo12345"
}
```

Response:

```json
{
  "id": 1,
  "name": "Demo Investor",
  "email": "investor@example.com"
}
```

Связь с моделью: модель не вызывается.

## `POST /auth/logout`

Назначение: очистить session.

Response:

```json
{
  "status": "ok"
}
```

Связь с моделью: модель не вызывается.

## `GET /auth/me`

Назначение: вернуть текущего пользователя по session cookie.

Response: `AuthUserResponse`.

Связь с моделью: модель не вызывается.

## `GET /opportunities`

Назначение: вернуть ранжированную ленту opportunities для UI.

Query:

| Параметр | Значение |
| --- | --- |
| `sort_by` | `score` или `undervaluation_percent`, default `score` |
| `limit` | `1..500`, default `100` |
| `output_currency` | только `RUB` |
| `fx_rate` | положительное число, но не используется |

Response:

```json
{
  "items": []
}
```

Каждый item имеет flattened shape `OpportunityItem`.

Важные особенности:

- Endpoint вызывает `ensure_listing_valuations(... only_missing=True ...)` перед чтением списка.
- Если в БД есть новые listings без valuation, будет выполнен backfill.
- DB-backed scoring пропускает невалидные rows, а не возвращает per-row ошибки.
- Explanations при backfill выключены, поэтому serializer может вернуть fallback summary.

Связь с моделью: косвенная через valuation backfill.

## `GET /shortlist`

Назначение: вернуть сохранённые пользователем объекты.

Query:

| Параметр | Значение |
| --- | --- |
| `output_currency` | только `RUB` |
| `fx_rate` | положительное число, но не используется |

Response: такой же `OpportunityListResponse`, как `/opportunities`.

Важные особенности:

- Требует authenticated session.
- Перед чтением также вызывает valuation backfill.
- Сортирует по `ShortlistItem.rank_position`, затем `Valuation.score`, затем `Listing.id`.

## `POST /shortlist`

Назначение: сохранить listing в shortlist.

Request:

```json
{
  "listing_id": 101,
  "rank_position": 1
}
```

Response:

```json
{
  "listing_id": 101,
  "saved": true
}
```

Важные особенности:

- Требует authenticated session.
- Если `rank_position` не передан, API ставит следующий rank для пользователя.
- Если listing не найден, возвращает HTTP 404.

Связь с моделью: перед сохранением вызывает valuation backfill для отсутствующих оценок.

## `DELETE /shortlist/{listing_id}`

Назначение: удалить listing из shortlist текущего пользователя.

Response:

```json
{
  "listing_id": 101,
  "saved": false
}
```

Связь с моделью: модель не вызывается.

## Geocode service

В репозитории также есть отдельный FastAPI сервис [`apps/geocode/api.py`](../../apps/geocode/api.py):

- `GET /health`
- `GET /geocode?address=...`
- `GET /reverse-geocode?latitude=...&longitude=...`

Это отдельное приложение на другом порту и не является частью `apps/api/api.py`.
