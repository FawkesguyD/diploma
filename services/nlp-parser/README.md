# services/nlp-parser

FastAPI-сервис «Парсер + NLP» дипломного АИС. Поток 2.2 плана — собирает
сообщения из Telegram/новостных/RSS/HTML источников, аннотирует их NLP-стабом,
публикует метрики в Kafka и отдаёт REST + SSE наружу.

## Что делает

* **REST `/api/auth`** — `POST /register`, `POST /login`, `GET /me`. JWT HS256,
  access-only, TTL 30 минут (см. `auth/jwt_tools.py`).
* **REST `/api/sources`** — CRUD источников + `POST /{id}/parse` (publish
  `ParseTelegramCommand` / `ParseNewsCommand` в `parser.exchange`, создаёт запись
  в `ops.parser_jobs`).
* **REST `/api/messages`** — list с cursor-пагинацией (`base64(ObjectId)`,
  sort `_id ASC`) и фильтрами (topic/district/sentiment/channel_kind/
  channel_site/source_id/since/until/is_ad), `GET /{id}`, `GET /stream` (SSE
  через in-process pub/sub с ping каждые 15 s).
* **REST `/api/subscriptions`** — list/create/delete подписок пользователя.
* **REST `/api/jobs/{id}`** — статус парсер-джобы.
* **RabbitMQ-worker** подписан на `parse.task.tg`, `parse.task.news` и
  `nlp.analyze` (топология — `infra/rabbitmq/definitions.json`):
  parse → upsert в Mongo `messages` → автопубликация `nlp.analyze` →
  NLP-аннотация → `annotated_messages` + Kafka `metrics.messages` + событие в
  in-process pub/sub для SSE.

## Стек

Python 3.11 · FastAPI · Pydantic v2 · Motor · SQLAlchemy[asyncpg] ·
aio-pika · aiokafka · PyJWT · bcrypt · sse-starlette.

## Контракты

Pydantic-модели общие с другими сервисами — в
[`services/_shared/contracts`](../_shared/contracts) (`aisi-contracts`):

* `aisi_contracts.messages` — `ParseTelegramCommand`, `ParseNewsCommand`,
  `AnalyzeMessageCommand`.
* `aisi_contracts.metrics.MessageMetric` — payload Kafka-топика
  `metrics.messages`.
* `aisi_contracts.envelope.Envelope` — общий конверт messaging-спеки.

## Конфигурация (env)

См. `nlp_parser/config.py`. Базовые переменные:

* `DATABASE_URL`, `MONGO_URL`, `MONGO_INITDB_DATABASE`
* `RABBITMQ_URL`, `KAFKA_BOOTSTRAP`
* `JWT_SECRET`, `JWT_ACCESS_TTL_SECONDS` (default 1800)
* `WORKER_PREFETCH` (default 8), `ENABLE_WORKER_ON_STARTUP` (default true)
* `NLP_MODEL_RUN_ID` (default `00000000-0000-0000-0000-000000000001`)
* `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, `TG_PARSE_LIMIT` (default 50) — если
  не заданы, TG-источники парсятся stub'ом.
* `HTTP_USER_AGENT`, `HTTP_TIMEOUT_SEC` (default 15) — для RSS/HTML-адаптеров.

## Адаптеры парсинга

Реестр выбирается по `core.sources.kind`
([`parsing/registry.py`](src/nlp_parser/parsing/registry.py)):

| kind   | Адаптер                | Что делает |
|--------|------------------------|------------|
| `tg`   | `parsing/telegram.py` (Telethon) → fallback `telegram_stub` | `iter_messages(handle, limit=TG_PARSE_LIMIT)`, `since`-фильтр. Без `TG_*` env — фикстуры. |
| `rss`  | `parsing/rss.py` (httpx + feedparser + BS4) | Скачивает фид, парсит entries, чистит HTML из `description`/`content`. |
| `html` | `parsing/html.py` (httpx + trafilatura + BS4) | `mode=single` — одна страница; `mode=index` + `link_selector` — обход анкоров одного домена. `max_articles` (default 10). |
| `news` | те же RSS/HTML с авто-детектом по URL | Для legacy `kind=news`. |

Конфиг конкретного источника (`core.sources.config` JSONB) для `html`:
```json
{"mode": "index", "link_selector": "a.article-link", "max_articles": 20}
```

### Генерация Telethon StringSession

```bash
docker run --rm -it diploma-nlp-parser python -m nlp_parser.scripts.tg_login \
  --api-id 12345 --api-hash deadbeef... --phone +79991234567
```
Скрипт распечатает строку `TG_SESSION=...` — кладёшь в `.env`.

## Запуск в составе compose

```bash
docker compose build nlp-parser
docker compose up -d nlp-parser
```

Health-чек: `GET http://localhost:8000/healthz`. Через Traefik —
`/api/auth/*`, `/api/sources/*`, `/api/messages/*`, `/api/subscriptions/*`,
`/api/jobs/*`.

## Тесты

```bash
docker run --rm -v "$PWD":/repo -w /repo python:3.11-slim bash -lc '
  pip install -q uv &&
  uv pip install --system -e services/_shared/contracts &&
  uv pip install --system -e services/nlp-parser[dev] &&
  pytest services/nlp-parser/tests -q
'
```

## TODO / known gaps

* Telegram: если `TG_*` env не заданы — `parsing/telegram_stub.py` с фикстурами.
* HTML: `trafilatura` хорошо работает на статьях; нестандартные SPA/JS-сайты
  потребуют per-source `link_selector` или отдельной реализации.
* NLP — `nlp/stub.py` (keyword-based классификатор/NER/sentiment). Боевая
  модель грузится тем же интерфейсом, версия пробрасывается в `MessageMetric`.
* Идемпотентность — `worker._processed_ids` in-memory; для нескольких реплик
  выносится в Redis/Mongo с TTL.
