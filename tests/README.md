# tests/ — интеграционные тесты системы

Этот каталог содержит **сквозные тесты** дипломного АИС, дополняющие per-service
unit-тесты в `services/*/tests/` и `model/tests/`.

## Структура

```
tests/
  api/           # HTTP end-to-end проверки запущенного compose-стенда
  frontend/     -> ../services/frontend/src (тесты живут рядом с кодом)
```

## Запуск

```bash
# 1. Поднять стенд (если ещё не запущен)
docker compose up -d

# 2. Засеять данные (один раз; идемпотентно)
python3 infra/seed/backfill_history.py
python3 infra/seed/backfill_mongo_objects.py

# 3. Прогнать e2e API-тесты против http://localhost
python3 -m pip install --user pytest httpx
pytest tests/api -q

# 4. Прогнать unit-тесты сервисов
pytest services/_shared/redis_lib/tests services/nlp-parser/tests \
       services/realestate/tests services/metrics/tests -q

# 5. Прогнать unit-тесты фронта
cd services/frontend && pnpm test
```

Подробнее по каждому модулю — в `services/*/README.md`.
