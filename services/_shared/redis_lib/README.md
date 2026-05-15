# aisi-redis

Общий Redis-клиент для сервисов АИС. Реализует две роли вспомогательного слоя:

- **Dedup** (`is_duplicate`) — атомарная идемпотентность через `SET NX EX`.
- **Outbound rate-limit** (`acquire_token`) — fixed-window счётчик per-host.

Источник правды по контрактам и стратегии отказов:
[`docs/design/databases/redis.md`](../../../docs/design/databases/redis.md) и
[ADR-0009](../../../docs/decisions/0009-redis-auxiliary-layer.md).

## Установка (editable)

```bash
pip install -e services/_shared/redis_lib
```

## Использование

```python
from aisi_redis import RedisSettings, get_client, is_duplicate, acquire_token

client = get_client(RedisSettings())

if not await is_duplicate(client, "msg", site="tg", external_id="123"):
    await acquire_token(client, host="telegram.org", max_per_min=100)
    ...
```

## Fail-mode

- `is_duplicate` → fail-open (`False` при недоступности Redis): дубль ловит Mongo upsert.
- `acquire_token` → fail-closed (`sleep 1s`): защита от ban'а внешним сайтом.
