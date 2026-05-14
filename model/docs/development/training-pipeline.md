# Пайплайн обучения

В проекте есть legacy pipeline и новый Russia 2021 pipeline. Runtime API сейчас ориентирован на Russia 2021 RUB artifact.

## Entrypoints

```bash
python -m ml.model.main --pipeline legacy
python -m ml.model.main --pipeline russia2021
python -m ml.model.main --pipeline db_russia2021
```

Совместимый entrypoint:

```bash
python main.py --pipeline russia2021
```

## Russia 2021 pipeline

Файл: [`ml/model/russia2021_training.py`](../../ml/model/russia2021_training.py).

Pipeline:

1. Читает локальный CSV или streaming dataset `daniilakk/Russia_Real_Estate_2021`.
2. Обрабатывает данные чанками, default `200000` rows.
3. Проверяет обязательные колонки: `rooms`, `area`, `kitchen_area`, `level`, `levels`, `price`.
4. Приводит source columns к numeric, где они доступны.
5. Фильтрует физически невозможные rows.
6. Строит `target_log_price = log(price)`.
7. Строит `target_log_price_per_m2 = log(price / area)`.
8. Создаёт общий feature frame через тот же `create_model_features()`, который используется inference.
9. Пишет CatBoost pools в `ml/artifacts/russia2021_prepared`.
10. Обучает CatBoost candidate.
11. Считает metrics и segment report.
12. Сохраняет model bundle в `ml/artifacts`.
13. Сохраняет reports в `ml/reports`.
14. Сохраняет readiness manifest.

## Target transform

Для нового Russia 2021 artifact используется точный `log(price)`, не `log1p(price)`.

В bundle это отражено как:

- `target_transform = "log"`;
- inverse transform в inference: `exp(prediction)`.

Legacy artifacts могут иметь implicit `log1p`, если `target_transform` отсутствует и `log_target = true`.

## Active feature config

Feature config для Russia 2021 создаётся в `russia2021_feature_config()`:

- numeric base: `rooms`, `area`, `kitchen_area`, `level`, `levels`, `latitude`, `longitude`;
- numeric derived: `is_studio`, `area_per_room`, `floor_ratio`, `is_top_floor`, `is_first_floor`, `kitchen_ratio`, `rooms_density`, `has_coordinates`;
- categorical: `building_type`, `object_type`, `region`.

Подробности: [model-inputs.md](../reference/model-inputs.md).

## Legacy pipeline

Legacy flow в `run_pipeline()`:

- читает старый dataset через `ml/model/data_loading.py`;
- использует `prepare_training_frame()` из `training_preprocessing.py`;
- обучает baseline и CatBoost;
- сохраняет `best_model.joblib`;
- использует `log1p` target transform;
- содержит старый feature set с `total_area_m2`, `floor`, `total_floors`, `district`, `seller_type` и другими полями.

Legacy artifacts поддерживаются loader, но не являются active runtime API.

## DB-backed training

`--pipeline db_russia2021`:

1. Экспортирует `normalized_listings` с `is_train_eligible = true` в CSV.
2. Для `price` берёт `price`, `listing_price` или `listing_price_rub`.
3. Запускает тот же Russia 2021 pipeline.

Файл экспорта: [`ml/model/db_training_data.py`](../../ml/model/db_training_data.py).

## Reports

Russia 2021 training сохраняет:

- `russia2021_training_report.json`;
- `russia2021_segment_metrics_report.json`;
- `russia2021_market_bounds.json`;
- prepared pools в `ml/artifacts/russia2021_prepared`.

Текущий committed report отражает active artifact, но часть новых полей metadata может добавляться readiness manifest отдельно.
