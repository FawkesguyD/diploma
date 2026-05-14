# Документация проекта

Этот каталог описывает фактическое состояние MVP-платформы для поиска вероятно недооценённых объектов недвижимости. Система считает model-based proxy valuation по данным объявлений и использует результат для ранжирования shortlist. Это не оценка подтверждённой цены сделки.

## Быстрый маршрут

- [Аудит текущего контракта](reference/audit-summary.md) — что было проверено и где лежит source of truth.
- [Входной контракт модели](reference/model-inputs.md) — какие поля реально принимает inference, какие значения допустимы и что игнорируется.
- [Выходной контракт модели](reference/model-outputs.md) — `price_outputs`, `delta_abs`, `delta_pct`, explainability и DB-backed поля.
- [API endpoints](reference/api-endpoints.md) — runtime ручки FastAPI и их связь с ML.
- [Артефакты модели](reference/artifacts.md) — `joblib`, readiness manifest, reports и prepared pools.
- [Известные проблемы](reference/known-issues.md) — train/inference skew, naming mismatch и валютные caveats.

## Разделы

- [Архитектура](architecture/README.md) — устройство репозитория и путь данных API -> ML.
- [Справочник](reference/audit-summary.md) — точные контракты, артефакты и ограничения.
- [Разработка](development/README.md) — локальный запуск, обучение и добавление признаков.
- [Деплой](deployment/README.md) — Docker, compose и runtime config.
- [Продукт](product/README.md) — рамки MVP и словарь терминов.

## Основные модули

- `apps/api` — основной FastAPI runtime API.
- `apps/ui` — React UI, который ожидает flattened opportunity shape.
- `apps/geocode` — отдельный сервис прямого и обратного геокодирования.
- `apps/normalization` — нормализация сырых объявлений в канонический payload.
- `services/data_migrator` — миграции, импорт CSV и первичный valuation backfill.
- `ml/model` — обучение, preprocessing, inference, validation, explainability и persistence.
- `ml/artifacts` — runtime model bundle, readiness manifest и prepared training pools.
- `shared/db` — SQLAlchemy-модели и DB session.

## Runtime source of truth

Для активного inference важны не только API-схемы, но и содержимое bundle:

- API загружает модель в [`apps/api/api.py`](../apps/api/api.py).
- Канонический inference находится в [`ml/model/inference.py`](../ml/model/inference.py).
- Подготовка признаков находится в [`ml/model/inference_preprocessing.py`](../ml/model/inference_preprocessing.py) и [`ml/model/normalization.py`](../ml/model/normalization.py).
- Валидация входа находится в [`ml/model/inference_validation.py`](../ml/model/inference_validation.py).
- Активный readiness manifest находится в [`ml/artifacts/model_readiness.json`](../ml/artifacts/model_readiness.json).

## Запуск и деплой

- Локальный запуск API: [development/local-setup.md](development/local-setup.md).
- Docker Compose: [deployment/docker.md](deployment/docker.md).
- Переменные окружения runtime: [deployment/runtime-config.md](deployment/runtime-config.md).

## Ограничения MVP

Короткая версия: система работает в RUB-only режиме, оценивает proxy valuation по признакам объявления и не обещает fair market price. Подробности: [product/mvp-scope.md](product/mvp-scope.md).
