# Жизненный цикл inference

## 1. Загрузка bundle

API вызывает `load_ready_model_bundle()`:

- читает `ml/artifacts/model_readiness.json`;
- проверяет `status in {"ready", "active"}`;
- разрешает `active_model_path`;
- при явном `MODEL_PATH` проверяет совпадение с manifest;
- загружает `joblib` через `load_model_bundle()`;
- проверяет `bundle.base_currency == "RUB"`;
- добавляет metadata из manifest к metadata bundle.

## 2. Validation и normalization

`validate_inference_record()`:

- применяет feature aliases (`total_area_m2 -> area`, `floor -> level` и т.д.);
- нормализует `building_type`, `object_type`, `region`;
- проверяет физические ограничения площади, кухни, комнат и этажности;
- проверяет координаты по границам РФ;
- выставляет `confidence` и `warnings`;
- возвращает errors для критичных нарушений.

## 3. Подготовка DataFrame

`prepare_inference_frame()` вызывает `create_model_features()`:

- повторно нормализует aliases для DataFrame;
- нормализует категориальные поля;
- вычисляет derived numeric features;
- приводит numeric columns через `pd.to_numeric(..., errors="coerce")`;
- оставляет только `feature_config.feature_columns`.

Для активной модели итоговый frame содержит 18 колонок.

## 4. Predict

Если bundle является CatBoost:

- categorical features заполняются строкой `missing`;
- модель вызывается как `bundle.model.predict(cat_frame)`.

Иначе модель вызывается на обычном frame.

## 5. Inverse transform

`inverse_transform_predictions()`:

- `identity` — без изменения;
- `log1p` — `expm1`;
- `log` — `exp`.

Активный Russia 2021 artifact использует `log`.

## 6. Price fields

`_price_fields_from_model_output()`:

- берёт `area`;
- если `prediction_target = "price_per_m2"`, model output трактуется как price/m²;
- иначе model output трактуется как total price;
- считает raw price/m²;
- применяет market bounds;
- возвращает `predicted_price_rub`, `price_per_m2_rub`, `bounds_result`.

Текущий active artifact имеет `prediction_target = "total_price"`.

## 7. Delta и response

`listing_price` не является ML feature. Он используется после prediction:

- `delta_abs = predicted_price_rub - listing_price_rub`;
- `delta_pct = delta_abs / listing_price_rub`, если listing price не равен 0.

Response всегда RUB-only.

## 8. Explanation

Если explanations включены:

- CatBoost SHAP используется для `top_factors`;
- факторы группируются по смысловым группам (`area`, `rooms`, `floor`, `building`, `region`);
- если SHAP недоступен, используется fallback explanation.

Если explanations выключены:

- `top_factors = []`;
- `explanation_summary` остаётся generic текстом.

## 9. Ranking

Batch ranking:

- сортировка по `delta_pct`, затем `delta_abs_rub`;
- выставляется `undervaluation_rank`.

DB ranking:

- результаты сохраняются в `valuations`;
- SQL пересчитывает `score` по позиции в общем списке `undervaluation_percent`;
- `score` не является модельным score.
