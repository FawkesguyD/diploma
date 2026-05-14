# Выходной контракт модели

Source of truth: [`ml/model/inference.py`](../../ml/model/inference.py), [`apps/api/api.py`](../../apps/api/api.py), [`shared/db/models.py`](../../shared/db/models.py), [`apps/ui/src/features/opportunities/api/opportunityMappers.ts`](../../apps/ui/src/features/opportunities/api/opportunityMappers.ts).

## Кратко

Runtime API возвращает RUB-only proxy valuation. Модель предсказывает значение в лог-шкале, затем inference делает inverse transform, переводит результат в цену объекта, применяет market bounds по цене за м² и считает delta относительно `listing_price`.

`score` не является output модели. Это DB ranking score, который пересчитывается по месту объекта в общем списке valuation rows.

## Базовая валюта

Активная runtime модель:

- `base_currency`: `RUB`
- `output_currency`: всегда `RUB`
- `fx_rate_used`: всегда `null`
- `price_outputs`: всегда только с ключом `RUB`

Поля `output_currency` и `fx_rate` сохранены в API ради совместимости, но валютная конвертация отключена.

## Постобработка

Последовательность:

1. CatBoost возвращает prediction в лог-шкале.
2. `target_transform = "log"` означает inverse transform через `exp(prediction)`.
3. Если metadata `prediction_target = "price_per_m2"`, результат умножается на `area`. Для текущего active artifact `prediction_target = "total_price"`.
4. Цена за м² считается как `predicted_total_price / area`.
5. Если в readiness metadata есть `market_bounds`, цена за м² клипуется по p05/p95 подходящего сегмента или global bounds.
6. Итоговая `predicted_price_rub = clamped_price_per_m2 * area`.
7. Если есть `listing_price`, считаются `delta_abs` и `delta_pct`.

Текущий readiness manifest содержит global market bounds:

| Метрика | Значение |
| --- | ---: |
| p05 | `27678.5714` RUB/m² |
| median | `61000.0` RUB/m² |
| p95 | `191935.4839` RUB/m² |

Если bounds применились, response получает warning `Применено рыночное ограничение цены за м².` и confidence может быть снижен.

## `price_outputs`

Форма:

```json
{
  "RUB": {
    "expected_price_proxy": 7000000.0,
    "comparison_currency": "RUB",
    "predicted_price_currency": "RUB",
    "listing_price_in_comparison_currency": 6500000.0,
    "delta_abs": 500000.0,
    "delta_pct": 0.0769230769
  }
}
```

Формулы:

- `expected_price_proxy = predicted_price_rub`
- `listing_price_in_comparison_currency = listing_price_rub`
- `delta_abs = expected_price_proxy - listing_price_rub`
- `delta_pct = delta_abs / listing_price_rub`, если `listing_price_rub != 0`

Если `listing_price` не передан, `listing_price_in_comparison_currency`, `delta_abs` и `delta_pct` равны `null` в direct inference.

## `/predict`

`POST /predict` возвращает `PredictionResponse`:

| Поле | Значение |
| --- | --- |
| `predicted_price_rub` | итоговая proxy-оценка объекта в RUB |
| `price_per_m2_rub` | итоговая цена за м² после market bounds |
| `listing_price_rub` | входной `listing_price`, если был |
| `delta_abs_rub` | разница `predicted_price_rub - listing_price_rub` |
| `delta_pct` | относительная разница |
| `confidence` | `high`, `medium` или `low` по validation warnings/errors и market bounds |
| `warnings` | предупреждения validation и postprocessing |
| `sanity_checks` | технические флаги: validation, market bounds, clamping, segment |
| `base_currency` | `RUB` |
| `output_currency` | `RUB` |
| `listing_price` | дублирует `listing_price_rub` для совместимости |
| `listing_currency` | `RUB` |
| `fx_rate_used` | `null` |
| `price_outputs` | валютный контейнер, сейчас только `RUB` |
| `top_factors` | список объясняющих факторов |
| `explanation_summary` | короткое текстовое объяснение |
| `valuation_note` | предупреждение, что это proxy valuation |

## `/predict/batch`

`POST /predict/batch` возвращает:

```json
{
  "count": 1,
  "ranked": true,
  "results": []
}
```

Каждый элемент `results` повторяет основные поля `/predict` и дополнительно содержит:

- `input_index` — исходный индекс объекта в batch.
- `listing_id` — если был во входе.
- `undervaluation_rank` — место после сортировки, если `rank_by_undervaluation = true`.

Сортировка batch: `delta_pct` по убыванию, затем `delta_abs_rub` по убыванию. Объекты без delta уходят вниз через `-inf`.

## DB-backed endpoint'ы

`GET /opportunities` и `GET /shortlist` возвращают flattened `OpportunityItem`, совместимый с UI mapper.

Дополнительные поля:

| Поле | Источник |
| --- | --- |
| `predicted_price` | `valuations.predicted_price` |
| `predicted_price_currency` | всегда `RUB` |
| `comparison_currency` | всегда `RUB` |
| `delta_abs` | пересчитанная разница в API serializer |
| `delta_pct` | пересчитанная относительная разница |
| `score` | DB ranking score после `_recalculate_valuation_scores` |
| `is_saved` | наличие записи в `shortlist_items` |
| `rank_position` | позиция в shortlist, только для saved flow |
| `source_url` | URL объявления из `listings` |

DB сохраняет:

- `predicted_price`
- `undervaluation_delta`
- `undervaluation_percent`
- `score`
- `confidence`
- `warnings`
- `sanity_checks`
- `explanation_summary`
- `top_factors`

## Explainability слой

Для CatBoost inference пытается получить SHAP values через `get_feature_importance(type="ShapValues")`. Затем факторы группируются, чтобы не отдавать несколько технических derived-фич одного смысла.

Если SHAP недоступен или падает, используется fallback explanation по базовым полям:

- площадь;
- комнаты;
- `region`;
- `district`;
- `building_type`;
- `object_type`.

Если explanations выключены, `top_factors` пустой, но `explanation_summary` всё равно заполняется generic текстом о proxy valuation и confidence.

## Что не является прямым output модели

- `delta_abs`, `delta_pct`: это postprocessing относительно listing price.
- `price_per_m2_rub`: производное поле после inverse transform и market bounds.
- `confidence`: результат validation/postprocessing, не CatBoost probability.
- `score`: DB ranking percentile-like score, не model score.
- `undervaluation_rank`: сортировка batch, не ML prediction.
- `explanation_summary`, `top_factors`: explainability слой поверх prediction.
