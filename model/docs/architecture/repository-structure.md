# Структура репозитория

Репозиторий устроен как MVP-монорепозиторий: runtime API, UI, ML, мигратор и shared DB слой живут рядом, но имеют разные зоны ответственности.

## Основные каталоги

| Путь | Назначение |
| --- | --- |
| `apps/api` | основной FastAPI сервис: auth, prediction endpoints, opportunities, shortlist, DB-backed valuation backfill |
| `apps/ui` | React UI; зависит от flattened `OpportunityItem` shape |
| `apps/geocode` | отдельный FastAPI сервис геокодирования |
| `apps/normalization` | нормализация сырых объявлений в канонический payload |
| `services/data_migrator` | ожидание БД, Alembic migrations, импорт CSV, seed demo user, первичный valuation backfill |
| `ml/model` | ML-код: training, inference, preprocessing, validation, persistence, readiness |
| `ml/artifacts` | `joblib` bundle, readiness manifest, prepared CatBoost pools |
| `ml/data/raw` | локальные исходные CSV для обучения |
| `ml/reports` | отчёты обучения, validation reports, generated shortlist/debug artifacts |
| `shared/db` | SQLAlchemy models и session factory |
| `docs` | инженерная документация |
| `tests` | contract и regression tests |
| `alembic` | миграции схемы PostgreSQL |

## Compatibility shims

Корневые thin wrappers сохранены для старых entrypoints:

| Файл | Что делает |
| --- | --- |
| `api.py` | экспортирует `app` из `apps.api.api`; сохраняет `uvicorn api:app` |
| `main.py` | вызывает `ml.model.main`; сохраняет `python main.py` |
| `train.py` | re-export из `ml.model.train` |
| `inference.py` | re-export из `ml.model.inference` |
| `preprocessing.py` | re-export из `ml.model.preprocessing` |
| `data_loading.py` | re-export из `ml.model.data_loading` |
| `evaluate.py` | re-export из `ml.model.evaluate` |
| `utils.py` | re-export из `ml.model.utils` |

Эти файлы не определяют новое поведение системы; они нужны для совместимости.

## Docker и build слой

| Файл | Назначение |
| --- | --- |
| `Dockerfile` | совместимый корневой API image |
| `apps/api/Dockerfile` | канонический Dockerfile API |
| `apps/ui/Dockerfile` | build UI и nginx runtime |
| `apps/geocode/Dockerfile` | image геокодера |
| `services/data_migrator/Dockerfile` | image мигратора/seed flow |
| `docker-compose.yml` | локальная сборка PostgreSQL, API, UI, geocode и migrator |
| `.github/workflows/ghcr.yml` | сборка/push контейнеров через явный matrix |

## Что реально определяет поведение

Runtime prediction определяют:

- `apps/api/api.py`
- `ml/model/readiness.py`
- `ml/model/inference.py`
- `ml/model/inference_preprocessing.py`
- `ml/model/normalization.py`
- `ml/model/inference_validation.py`
- `ml/model/category_normalization.py`
- `ml/model/feature_schema.py`
- `ml/artifacts/model_readiness.json`
- `ml/artifacts/best_model_russia2021.joblib`

Training определяют:

- `ml/model/main.py`
- `ml/model/russia2021_training.py`
- `ml/model/training.py`
- `ml/model/training_preprocessing.py`
- `ml/model/db_training_data.py`

DB/UI контракт определяют:

- `shared/db/models.py`
- `apps/api/api.py`
- `apps/ui/src/features/opportunities/api/opportunityMappers.ts`
