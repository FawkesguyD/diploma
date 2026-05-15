# Redis — спецификация (вспомогательный слой)

> Решение зафиксировано в [ADR-0009](../../decisions/0009-redis-auxiliary-layer.md).
> Контейнер: `redis:7-alpine`, порт `6379`, AOF-durability, single-node.

Redis в системе используется **только** для двух ролей: идемпотентность (dedup) и outbound rate-limit. Бизнес-данные (сообщения, объекты, метрики) живут в Mongo / Postgres / ClickHouse и не дублируются в Redis.

---

## 1. Конфигурация

| Параметр | Значение | Зачем |
|---|---|---|
| `appendonly yes` | AOF включён | Durability при рестарте |
| `appendfsync everysec` | fsync раз в секунду | Потеря ≤1с при kill -9, минимум overhead |
| `maxmemory 256mb` | Жёсткий лимит RAM | Кэш не разрастётся, dedup-ключи под TTL |
| `maxmemory-policy allkeys-lru` | LRU eviction | Старые ключи вытесняются при упоре в лимит |
| `requirepass ${REDIS_PASSWORD}` | Auth | Best practice, обязательно |
| `restart: unless-stopped` | Авто-restart | Как у других сервисов |

Один логический namespace (`db=0`), разделение через **префиксы ключей**.

---

## 2. Контракты ключей

### 2.1 Dedup (идемпотентность)

| Префикс | Полный пример | Тип | TTL | Команды | Источник |
|---|---|---|---|---|---|
| `dedup:msg:{site}:{ext_id}` | `dedup:msg:tg:badaevsky_complex:12345` | string `"1"` | `86400s` (24h) | `SET NX EX` | `ingester` (TG/RSS) |
| `dedup:obj:{site}:{ext_id}` | `dedup:obj:avito.ru:6700123` | string `"1"` | `86400s` | `SET NX EX` | `ingester` (RE) |
| `dedup:annotate:{msg_id}` | `dedup:annotate:507f1f77bcf86cd799439011` | string `"1"` | `3600s` (1h) | `SET NX EX` | `nlp-parser` |
| `dedup:eval:{obj_id}` | `dedup:eval:6a0000000000000000000016` | string `"1"` | `3600s` | `SET NX EX` | `realestate` |

**Семантика:** `SET key "1" NX EX <ttl>` возвращает `OK` если ключ создан (новое событие) и `nil` если ключ уже существовал (дубль). Атомарность гарантирует Redis — race condition между параллельными воркерами невозможен.

**TTL логика:**
- 24ч для входящих сообщений/объектов — покрывает любой реалистичный re-poll внешнего источника + retry RabbitMQ.
- 1ч для аннотации/оценки — типичный SLA на обработку, дольше держать незачем.

### 2.2 Rate-limit (outbound)

| Ключ | Тип | TTL | Команды | Источник |
|---|---|---|---|---|
| `ratelimit:src:{host}` | int counter | `60s` | `INCR` / `EXPIRE` / `TTL` | `ingester`, `realestate` |

**Семантика:** sliding-window-приближение через fixed-window. На каждый исходящий запрос — `INCR` + `EXPIRE 60` если ключ был создан только что. При `cur > limit` — `sleep(TTL)` и retry.

**Ограничение точности:** ±60с погрешность на границе окна. Для защиты от ban'а приемлемо. Для billing-точности нужен sorted-set sliding-window (отложено до появления реальной потребности).

---

## 3. Naming convention

Формат: `<purpose>:<domain>:<id>` всегда.

- `<purpose>` — `dedup`, `ratelimit`, в будущем `cache`, `pubsub`, `lock`.
- `<domain>` — поддомен внутри purpose (`msg`, `obj`, `src`, `annotate`, `eval`).
- `<id>` — уникальный ключ внутри domain (`{site}:{ext_id}`, `{host}`, `{msg_id}`).

**Запрещено:**
- ключи без префикса (`12345`, `userdata`);
- camelCase (`dedupMsg:tg:...`);
- использование `:` внутри `<id>` без явного контекста (например, `tg:badaevsky_complex:12345` — OK, потому что site=tg, channel=badaevsky_complex, id=12345 разбираются однозначно справа).

---

## 4. Лимиты per-host (rate-limit)

Источник конфигурации: `infra/seed/source_limits.json` (создаётся при реализации).

```json
{
  "telegram.org": 100,
  "avito.ru": 30,
  "cian.ru": 30,
  "ria.ru": 60,
  "rbc.ru": 60,
  "default": 30
}
```

**Логика выбора:**
1. Извлечь `host` из URL источника (`urlparse(source.url_or_handle).netloc` или `source.channel_site`).
2. Найти `host` в словаре. Если нет — взять `default`.
3. Передать в `acquire_token(host, max_per_min)`.

Лимиты — на основе публичных ToS и эмпирики, корректируются при появлении 429/ban.

---

## 5. Алгоритмы (псевдокод)

### 5.1 `is_duplicate`

```python
async def is_duplicate(site: str, external_id: str, ttl: int = 86400) -> bool:
    """
    True  → дубль, пропустить обработку.
    False → новое, продолжать.
    Fail-open: при недоступности Redis возвращает False (Mongo upsert ловит дубли).
    """
    key = f"dedup:msg:{site}:{external_id}"
    try:
        was_set = await redis.set(key, "1", ex=ttl, nx=True)
        return was_set is None
    except RedisError as e:
        log.warning("redis_unavailable_dedup_fallback", error=str(e), key=key)
        return False
```

### 5.2 `acquire_token`

```python
async def acquire_token(host: str, max_per_min: int) -> None:
    """
    Блокирует до получения токена.
    Fail-closed: при недоступности Redis sleep 1с (защита от ban'а).
    """
    key = f"ratelimit:src:{host}"
    try:
        cur = await redis.incr(key)
        if cur == 1:
            await redis.expire(key, 60)
        if cur > max_per_min:
            wait = await redis.ttl(key)
            log.info("ratelimit_hit", host=host, cur=cur, wait=wait)
            await asyncio.sleep(max(wait, 1))
            return await acquire_token(host, max_per_min)
    except RedisError as e:
        log.warning("redis_unavailable_ratelimit_fallback", error=str(e), host=host)
        await asyncio.sleep(1)
```

---

## 6. Стратегия отказов (fail mode таблица)

| Ситуация | Поведение | Последствие |
|---|---|---|
| Redis healthy | dedup отсекает до Mongo, ratelimit считает в shared counter | Норма |
| Redis недоступен (network/down) | dedup → fail-open (False), ratelimit → fail-closed (sleep 1с) | Парсинг продолжает работать; дубли ловит Mongo upsert; outbound ограничен sleep 1с (~60 RPM на воркер) |
| Redis рестартует с потерей AOF | Все ключи теряются | Окно дублей (~24ч могут пройти повторно), Mongo upsert ловит. Rate-limit обнуляется (короткий burst) |
| `maxmemory` исчерпан | LRU evict старых ключей | Самые старые dedup-ключи удаляются раньше TTL → возможен дубль; Mongo upsert ловит |
| Сетевой таймаут на одной операции | `socket_timeout` → исключение | Логируется + fallback по схеме выше |

**Главный принцип:** Redis — **производный слой**, не critical path. При его отказе **корректность** не нарушается (только производительность).

---

## 7. Мониторинг и наблюдаемость

### 7.1 Health-check

`docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
  interval: 5s
  timeout: 3s
  retries: 5
```

### 7.2 Метрики для логирования

В сервисах через структурированные логи:
- `dedup_skip` — счётчик пропущенных дубликатов (per channel/site).
- `dedup_check_latency_ms` — гистограмма латентности.
- `ratelimit_hit` — счётчик упоров в лимит (per host).
- `redis_unavailable_dedup_fallback` / `redis_unavailable_ratelimit_fallback` — счётчик деградаций.

### 7.3 Команды для отладки

```bash
docker compose exec redis redis-cli -a $REDIS_PASSWORD INFO memory
docker compose exec redis redis-cli -a $REDIS_PASSWORD DBSIZE
docker compose exec redis redis-cli -a $REDIS_PASSWORD KEYS 'dedup:*' | head
docker compose exec redis redis-cli -a $REDIS_PASSWORD KEYS 'ratelimit:*'
docker compose exec redis redis-cli -a $REDIS_PASSWORD MONITOR     # live-trace
```

---

## 8. Что НЕ хранится в Redis (явный negative scope)

| Данные | Где живут | Почему не Redis |
|---|---|---|
| Сообщения, NLP-аннотации | MongoDB | Долгоживущие документы, нужны индексы и change streams |
| Объявления, оценки | MongoDB | Аналогично |
| Пользователи, источники, jobs | PostgreSQL | Транзакции, FK, durability важнее latency |
| События метрик | Kafka → ClickHouse | Append-only event log с retention |
| Артефакты моделей | MinIO | Бинарники, версионирование |
| JWT-сессии / blacklist | (stateless JWT) | Решено в [ADR-0006](../../decisions/0006-tech-stack.md) |
| Кэш дашбордов | (нет, прямые запросы к CH) | Нагрузка не требует кэша на текущем масштабе. Возможный будущий ADR-0010 |
| Pub/sub для SSE | (Mongo polling сейчас) | Возможный будущий ADR-0011, не входит в скоуп ADR-0009 |

---

## 9. Связанные документы

- [ADR-0009](../../decisions/0009-redis-auxiliary-layer.md) — обоснование решения, альтернативы, последствия.
- [container.puml](../../architecture/container.puml) — Redis в контейнерной диаграмме.
- [component.puml](../../architecture/component.puml) — Redis client как компонент в `nlp-parser` / `realestate`.
- [deployment.puml](../../architecture/deployment.puml) — Redis в `internal` сети, порт 6379.
- [sequence-redis-ingest.puml](../../architecture/sequence-redis-ingest.puml) — пошаговый сценарий парсинга с Redis.
- [План реализации](/Users/daniel/Projects/%D0%94%D0%98%D0%9F%D0%9B%D0%9E%D0%9C/.sisyphus/plans/redis-dedup-ratelimit.md) — этапы, оценка, acceptance criteria.
