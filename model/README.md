# MVP-платформа анализа недвижимости

Репозиторий содержит текущий MVP для proxy valuation недвижимости и подготовлен к постепенному росту в сторону нескольких модулей внутри одного монорепозитория. Сейчас в репозитории уже выделены отдельный API-модуль и ML-часть; позже рядом можно добавлять `apps/ui` и другие сервисы без смены базовой структуры.

## Структура репозитория

```text
.
├── apps/
│   ├── api/                 # FastAPI-модуль и его Dockerfile
│   ├── analytics_service/   # отдельный сервис инвест-аналитики /score
│   ├── geocode/             # прямое и обратное геокодирование
│   └── normalization/       # нормализация сырых объектов
├── docs/
│   ├── api/
│   ├── architecture/
│   ├── deployment/
│   └── ml/
├── ml/
│   ├── artifacts/           # сохранённые model bundles для inference
│   ├── data/raw/            # локальная копия датасета
│   ├── model/               # training/inference код
│   └── reports/             # отчёты обучения и shortlist
├── .github/workflows/
├── api.py                   # совместимый entrypoint для uvicorn api:app
├── main.py                  # совместимый entrypoint для python main.py
├── docker-compose.yml
└── requirements.txt
```

## Какие модули уже есть

- `apps/api` — текущий FastAPI сервис с ручками `/`, `/health`, `/predict`, `/predict/batch`, `/opportunities`, `/shortlist`.
- `apps/analytics_service` — отдельный FastAPI сервис `/score` для `price_per_meter`, `formula`, `regression` аналитики.
- `apps/geocode` — сервис `address -> coordinates` и `coordinates -> normalized address`.
- `apps/normalization` — явный слой нормализации категорий, адресов и feature aliases.
- `ml/model` — код обучения, inference, explainability и подготовки данных.
- `ml/artifacts` — бинарные артефакты модели и readiness manifest, используемые API по умолчанию.

## Где лежат артефакты модели

Артефакты вынесены в `ml/artifacts`, потому что это служебные бинарные результаты ML-пайплайна, а не часть API-кода. Такое разделение оставляет рядом:

- код модели в `ml/model`
- локальные данные в `ml/data/raw`
- отчёты обучения в `ml/reports`
- model bundles для инференса в `ml/artifacts`

По умолчанию API и Docker используют readiness manifest `ml/artifacts/model_readiness.json`, который указывает на активный RUB-артефакт `ml/artifacts/best_model_russia2021.joblib`. Если артефакты станут слишком тяжёлыми для хранения в Git, структура уже готова для переноса их во внешний storage без перемешивания с кодом.

## Локальный запуск API

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
```

Запуск через совместимый корневой entrypoint:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Канонический модульный запуск:

```bash
uvicorn apps.api.api:app --host 0.0.0.0 --port 8000
```

Запуск через Docker Compose:

```bash
docker compose up --build
```

Отдельный сервис аналитики доступен на `${ANALYTICS_PORT:-8090}`:

```bash
uvicorn apps.analytics_service.api:app --host 0.0.0.0 --port 8090
```

Пример regression-запроса:

```bash
curl -X POST "http://localhost:8090/score?method=regression" \
  -H "Content-Type: application/json" \
  -d '{"rooms":2,"area":54,"kitchen_area":9,"level":5,"levels":12,"listing_price":9000000,"listing_currency":"RUB"}'
```

## Локальный запуск ML-пайплайна

Совместимый запуск:

```bash
python main.py --pipeline russia2021
```

Канонический запуск:

```bash
python -m ml.model.main --pipeline russia2021
```

Запуск обучения из нормализованного слоя БД:

```bash
python -m ml.model.main --pipeline db_russia2021
```

## Runtime-валюта и готовность модели

Система после нормализации работает только в RUB. Валютная конвертация отключена: `USD`, `BOTH`, `fx_rate` и `fx_rate_used` больше не участвуют в расчётах. API загружает только модель со статусом `ready` или `active`; если readiness manifest отсутствует или указывает на неготовую модель, prediction endpoints возвращают operational error.

## CI/CD

Workflow [`ghcr.yml`](./.github/workflows/ghcr.yml) собирает и публикует контейнеры модулей через явный `matrix`. Сейчас в matrix добавлен только `api`, но структура готова для новых модулей.

Что делает workflow:

- запускается только на релевантные изменения в `apps/**`, `ml/**`, workflow-файлах, `docker-compose.yml`, `requirements.txt`, `Dockerfile`
- билдит каждый модуль в своей matrix-ветке параллельно
- пушит образы в GHCR параллельно
- использует отдельный тег образа на модуль, например `ghcr.io/<owner>/<repo>-api`

Документация по архитектуре, API, ML и деплою лежит в [`docs/`](./docs).
