# Поток API -> ML

Эта страница описывает путь данных от HTTP request до ответа API.

## Прямой `/predict`

1. FastAPI валидирует envelope `SinglePredictionRequest`.
2. `get_model_bundle()` загружает active bundle через readiness manifest и кеширует его.
3. `predict_proxy_valuation_from_bundle()` проверяет `output_currency`; допустим только `RUB`.
4. `_build_response()` запускает `validate_inference_record()`.
5. Validation нормализует алиасы и категории.
6. `prepare_inference_frame()` строит DataFrame с колонками active `feature_config`.
7. CatBoost получает frame и возвращает prediction в лог-шкале.
8. `inverse_transform_predictions()` применяет `exp()` для `target_transform = "log"`.
9. Inference считает price/m² и применяет market bounds.
10. Runtime собирает `price_outputs`, delta, confidence, warnings и explanation.
11. FastAPI сериализует `PredictionResponse`.

Если validation возвращает errors, endpoint отдаёт HTTP 400.

## Batch `/predict/batch`

1. FastAPI валидирует `BatchPredictionRequest`.
2. Для каждого объекта API добавляет `input_index`.
3. `score_proxy_valuations_from_bundle()` последовательно вызывает тот же `_build_response()`.
4. Каждый результат получает `listing_id`, `input_index`, `price_outputs`, confidence и service fields.
5. Если `rank_by_undervaluation = true`, результаты сортируются по `delta_pct`, затем `delta_abs_rub`.
6. API возвращает `BatchPredictionResponse`.

Важно: batch не частично устойчивый. Один невалидный объект приводит к HTTP 400 для всего запроса.

## DB-backed valuation flow

Этот flow используется в `/opportunities`, `/shortlist` и bootstrap мигратора.

1. API вызывает `ensure_listing_valuations(session, only_missing=True/False)`.
2. `_build_valuation_listing_query()` читает rows из `listings`.
3. `_build_scoring_payload()` вызывает `build_listing_model_payload()`.
4. Payload строится только из тех полей, которые поддерживает active `feature_config`.
5. `validate_inference_record()` проверяет каждый payload.
6. Невалидные rows пропускаются и логируются.
7. Валидные rows идут в `score_proxy_valuations_from_bundle(... rank_results=False ...)`.
8. Результаты upsert-ятся в `valuations`.
9. `_recalculate_valuation_scores()` пересчитывает `score` по глобальному ranking.
10. `/opportunities` и `/shortlist` читают joined `listings + valuations + shortlist_items`.
11. `_serialize_opportunity()` отдаёт flattened `OpportunityItem` для UI.

## Главное отличие direct и DB-backed

Direct API может получить полный payload с `object_type`, `region`, `kitchen_area`, координатами и listing price.

DB-backed scoring зависит от того, что есть в `listings`. Сейчас `object_type` и `region` в этой таблице отсутствуют, поэтому модель часто получает `missing` категории. Это не ломает inference, но снижает confidence и качество сигнала.

## Где искать контракты

- Входы модели: [model-inputs.md](../reference/model-inputs.md).
- Выходы модели: [model-outputs.md](../reference/model-outputs.md).
- Формы endpoint'ов: [api-endpoints.md](../reference/api-endpoints.md).
