# Добавление новых признаков

Эта страница описывает безопасный порядок добавления признаков.

## Главное правило

Не добавляйте признак только в API payload или только в training code. Признак должен пройти один и тот же путь:

```text
raw/input field -> alias normalization -> create_model_features -> feature_config -> train artifact -> inference frame
```

## Шаги

1. Добавьте имя признака или alias в [`ml/model/feature_schema.py`](../../ml/model/feature_schema.py).
2. Если нужен alias, добавьте его в `FEATURE_ALIASES`.
3. Если признак приходит из DB, добавьте mapping в `LISTING_TO_MODEL_FIELD_MAP` и убедитесь, что query в `apps/api/api.py` выбирает source column.
4. Если признак derived, вычисляйте его в [`ml/model/normalization.py`](../../ml/model/normalization.py), а не отдельно в training и inference.
5. Добавьте validation rule в [`ml/model/inference_validation.py`](../../ml/model/inference_validation.py), если значение может быть физически невозможным.
6. Для categorical признака добавьте нормализацию/справочник в [`ml/model/category_normalization.py`](../../ml/model/category_normalization.py).
7. Обновите Russia 2021 feature config или legacy feature config.
8. Переобучите artifact и обновите readiness manifest.
9. Обновите [model-inputs.md](../reference/model-inputs.md) и tests.

## Что нельзя делать

- Не рассчитывать один и тот же derived feature в двух местах.
- Не полагаться на extra keys в `object_features`: модель видит только `feature_config.feature_columns`.
- Не менять имена public функций без adapter.
- Не менять response shape `/predict`, `/predict/batch`, `/opportunities`, `/shortlist` без явного compatibility слоя.
- Не добавлять новые валюты в docs/UI до реальной поддержки в `ml/model/inference.py`.

## Проверки перед merge

Минимально проверьте:

```bash
python -m unittest discover tests
```

Для ML feature changes отдельно проверьте:

- прямой `/predict` с canonical field names;
- прямой `/predict` с aliases;
- DB-backed payload через `build_listing_model_payload`;
- loading старого `joblib`, если менялся persistence/feature config.

## Документация

После добавления признака обновите:

- [model-inputs.md](../reference/model-inputs.md);
- [known-issues.md](../reference/known-issues.md), если появился временный рассинхрон;
- [artifacts.md](../reference/artifacts.md), если изменился bundle schema или readiness manifest.
