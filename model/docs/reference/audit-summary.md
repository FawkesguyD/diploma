# Итоги аудита

Дата аудита: 2026-04-17.

## Кратко

Фактический runtime контракт модели определяется связкой FastAPI API, inference preprocessing, validation layer и активного `joblib` bundle. Активная модель в текущем состоянии проекта — `ml/artifacts/best_model_russia2021.joblib`, но API загружает её через readiness manifest `ml/artifacts/model_readiness.json`.

Главный вывод: модель не принимает произвольный `dict`. Активный CatBoost ожидает фиксированный набор из 18 признаков: 15 числовых и 3 категориальных. `listing_price`, `listing_currency`, `output_currency`, `fx_rate`, `listing_id` и `input_index` не являются ML features; они нужны для postprocessing, совместимости API и ранжирования.

## Источники истины

| Вопрос | Фактический источник |
| --- | --- |
| Runtime API | [`apps/api/api.py`](../../apps/api/api.py) |
| Загрузка активной модели | [`ml/model/readiness.py`](../../ml/model/readiness.py), [`ml/artifacts/model_readiness.json`](../../ml/artifacts/model_readiness.json) |
| Канонический inference | [`ml/model/inference.py`](../../ml/model/inference.py) |
| Подготовка inference frame | [`ml/model/inference_preprocessing.py`](../../ml/model/inference_preprocessing.py), [`ml/model/normalization.py`](../../ml/model/normalization.py) |
| Схема признаков и алиасы | [`ml/model/feature_schema.py`](../../ml/model/feature_schema.py) |
| Runtime validation | [`ml/model/inference_validation.py`](../../ml/model/inference_validation.py) |
| Категориальные справочники | [`ml/model/category_normalization.py`](../../ml/model/category_normalization.py) |
| DB -> model payload | [`ml/model/runtime_adapters.py`](../../ml/model/runtime_adapters.py), [`apps/api/api.py`](../../apps/api/api.py) |
| Training pipeline Russia 2021 | [`ml/model/russia2021_training.py`](../../ml/model/russia2021_training.py) |
| Legacy training pipeline | [`ml/model/main.py`](../../ml/model/main.py), [`ml/model/training.py`](../../ml/model/training.py), [`ml/model/training_preprocessing.py`](../../ml/model/training_preprocessing.py) |
| DB persistence contract | [`shared/db/models.py`](../../shared/db/models.py) |
| UI flattened opportunity contract | [`apps/ui/src/features/opportunities/api/opportunityMappers.ts`](../../apps/ui/src/features/opportunities/api/opportunityMappers.ts) |

## Runtime артефакт

Активный manifest:

- path: `ml/artifacts/model_readiness.json`
- status: `active`
- active model path: `best_model_russia2021.joblib`
- base currency: `RUB`
- target formula в manifest: `F(x)=log(price)`
- global market bounds: p05 `27678.5714`, p95 `191935.4839` RUB/m²

Активный bundle:

- path: `ml/artifacts/best_model_russia2021.joblib`
- model class: `catboost.core.CatBoostRegressor`
- model name: `catboost_regressor_russia2021`
- target column: `price`
- target transform: `log`
- base currency: `RUB`
- feature columns: `rooms`, `area`, `kitchen_area`, `level`, `levels`, `latitude`, `longitude`, `is_studio`, `area_per_room`, `floor_ratio`, `is_top_floor`, `is_first_floor`, `kitchen_ratio`, `rooms_density`, `has_coordinates`, `building_type`, `object_type`, `region`

## Найденные точки интеграции

- `POST /predict` вызывает `predict_proxy_valuation_from_bundle`.
- `POST /predict/batch` вызывает `score_proxy_valuations_from_bundle`.
- `GET /opportunities` и `GET /shortlist` перед чтением данных вызывают `ensure_listing_valuations`, который делает DB-backed scoring/backfill.
- `services/data_migrator/bootstrap.py` импортирует `ensure_listing_valuations` из API и тем самым зависит от текущего inference flow.
- Root wrappers `api.py`, `main.py`, `train.py`, `inference.py`, `preprocessing.py`, `data_loading.py`, `evaluate.py`, `utils.py` являются compatibility слоями.

## Найденные риски

- В текущем коде API default model path указывает на `best_model_russia2021.joblib`; старые утверждения про fallback на `best_model.joblib` устарели для runtime API.
- `MODEL_PATH` не является свободным override: если он задан явно, readiness loader требует, чтобы он совпадал с active model path из manifest.
- Активный bundle сам по себе не содержит `category_values` и `market_bounds`; эти данные добавляются при загрузке через readiness manifest. Прямой `load_model_bundle` даёт меньше metadata, чем API runtime.
- Сохранённый `ml/artifacts/russia2021_prepared/train_pool.csv` содержит `building_type` и `object_type` в числовых кодах, а текущий runtime preprocessing нормализует эти поля в текстовые значения. Это потенциальный train/inference skew.
- Training preprocessing допускает `rooms = -1` как studio marker, но runtime validation считает отрицательное количество комнат ошибкой. Для runtime studio безопаснее передавать `rooms = 0`.
- DB-backed scoring получает не все активные признаки: `object_type`, `region` и часто `kitchen_area` отсутствуют в `listings`, поэтому такие объекты проходят с warnings и более низким confidence.

## Что нужно было изменить в документации

- Зафиксировать активный список ML features отдельно от API service-only полей.
- Описать допустимые значения числовых и категориальных параметров по фактической validation logic.
- Отдельно описать различия direct `/predict`, `/predict/batch` и DB-backed valuation flow.
- Обновить API docs под RUB-only контракт.
- Документировать readiness manifest как часть runtime source of truth.
- Явно вынести known issues, чтобы новые изменения не маскировали текущие рассинхроны.
