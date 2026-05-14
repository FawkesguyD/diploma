# Словарь терминов

## Listing price

Цена объявления, пришедшая из источника или direct API. В коде это `listing_price`. Она не является ML feature активной модели и используется для postprocessing.

## Expected price proxy

Итоговая модельная оценка цены объекта в RUB после inverse transform и market bounds. В response это `expected_price_proxy` внутри `price_outputs.RUB`.

## Proxy valuation

Оценка по данным объявлений, а не подтверждённая цена сделки. В проекте это основной режим модели.

## Delta abs

Абсолютная разница:

```text
delta_abs = expected_price_proxy - listing_price
```

В direct response поле называется `delta_abs_rub`, а внутри `price_outputs.RUB` — `delta_abs`.

## Delta pct

Относительная разница:

```text
delta_pct = delta_abs / listing_price
```

Если listing price отсутствует или равен 0, direct inference не может корректно посчитать процент.

## Shortlist

Сохранённый пользователем список объектов из opportunities feed. В БД это `shortlist_items`.

## Opportunity ranking

Порядок объектов по потенциальной недооценённости. В batch используется сортировка по `delta_pct`, затем `delta_abs_rub`. В DB-backed endpoints используется `Valuation.score` и/или `undervaluation_percent`.

## Score

DB ranking score в таблице `valuations`. Это не output модели. API пересчитывает score SQL-запросом по позиции объекта в общем ranking.

## Explanation summary

Короткий текст, объясняющий оценку. Может быть построен на SHAP для CatBoost или fallback logic, если SHAP недоступен.

## Top factors

Список факторов, которые сильнее всего повлияли на proxy valuation по explainability layer. Это не causal proof и не guarantee.

## Market bounds

Ограничения цены за м² по p05/p95 из train distribution. Runtime применяет их после prediction, чтобы отсечь экстремальные значения.

## Confidence

Качество входного payload с точки зрения validation и postprocessing: `high`, `medium`, `low`. Это не вероятность корректности прогноза.
