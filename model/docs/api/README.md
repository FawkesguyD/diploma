# API

Этот раздел оставлен как совместимая точка входа для старых ссылок.

Актуальная документация перенесена:

- [API endpoints](../reference/api-endpoints.md)
- [Model inputs](../reference/model-inputs.md)
- [Model outputs](../reference/model-outputs.md)
- [API -> ML flow](../architecture/api-ml-flow.md)

Код основного API находится в [`apps/api/api.py`](../../apps/api/api.py). Корневой [`api.py`](../../api.py) остаётся thin wrapper для `uvicorn api:app`.
