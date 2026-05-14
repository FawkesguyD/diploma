# Известные проблемы

Эта страница фиксирует реальные рассинхроны, найденные в коде, артефактах и runtime flow. Это не список желаемых улучшений, а практические caveats для разработки.

## Путь active model отличается от старого контракта

Текущий `apps/api/api.py`, Dockerfile и compose указывают на `ml/artifacts/best_model_russia2021.joblib`. Runtime загрузка идёт через `ml/artifacts/model_readiness.json`.

Старые утверждения про дефолтный `ml/artifacts/best_model.joblib` больше не описывают активный API runtime.

## `MODEL_PATH` не свободный fallback

Если `MODEL_PATH` задан явно, `load_ready_model_bundle` проверяет, что этот путь совпадает с `active_model_path` из readiness manifest. Иначе API получает `ModelReadinessError`.

Практический вывод: для переключения модели нужно обновлять readiness manifest, а не только env var.

## Metadata в bundle и readiness manifest различаются

`best_model_russia2021.joblib` содержит feature config, target transform и метрики, но не содержит `category_values` и `market_bounds`. Эти данные есть в `model_readiness.json` и добавляются к bundle только при загрузке через `load_ready_model_bundle`.

Последствие:

- API runtime видит market bounds и allowed regions.
- Прямой `load_model_bundle("ml/artifacts/best_model_russia2021.joblib")` видит неполную metadata.

## Возможный categorical train/inference skew

Сохранённый `ml/artifacts/russia2021_prepared/train_pool.csv` содержит `building_type` и `object_type` как числовые категории (`0`, `1`, `2`, `3`, `4`, `5`, `11`). Текущий runtime preprocessing нормализует эти поля в текстовые значения (`panel`, `monolith`, `secondary`, `new` и т.д.).

CatBoost принимает unseen categorical strings, поэтому inference не ломается, но качество может отличаться от training distribution. Перед следующим релизом модели нужно переобучить артефакт текущим preprocessing кодом или зафиксировать backward-compatible numeric categorical mode.

## `rooms = -1` расходится между training и runtime

Russia 2021 preprocessing допускает `rooms >= -1`, а `create_model_features` считает `rooms <= 0` студией. Runtime validation при этом отклоняет `rooms < 0`.

Практический безопасный вариант для API: передавать `rooms = 0` для студии. `rooms = -1` не использовать в direct runtime payload.

## DB-backed scoring не получает все активные признаки

`ensure_listing_valuations` строит payload из таблицы `listings`. В текущей таблице нет `object_type` и `region`, а `kitchen_area_m2` часто не заполняется импортёром `office-sale.csv`.

Последствия:

- `object_type` и `region` часто становятся `missing`;
- confidence снижается из-за warnings;
- market bounds применяются по global сегменту;
- DB-backed оценка может отличаться от direct `/predict`, если direct payload содержит полный набор признаков.

## `price`, `listing_price`, `price_usd` имеют разную историческую семантику

Для активного runtime:

- `listing_price` — правильное поле для цены объявления и delta;
- `price` — target column Russia 2021 и только fallback для listing price в активном bundle, если `listing_price` не передан;
- `price_usd` — legacy target старых артефактов, не listing price для активной модели.

Новые payloads должны использовать `listing_price`.

## Direct batch не частично устойчивый

`/predict/batch` не возвращает per-row errors. Если один объект не проходит validation, весь batch endpoint возвращает HTTP 400.

DB-backed flow ведёт себя иначе: невалидные rows пропускаются и логируются.

## RUB-only поля выглядят как мультивалютные

В API всё ещё есть `output_currency`, `fx_rate`, `fx_rate_used`, `price_outputs` и `comparison_currency`, но runtime принимает и возвращает только RUB.

Причина: сохранена совместимость внешнего response shape. Не добавляйте USD/BOTH в документацию или UI, пока валютная конвертация реально не возвращена в код.

## Старые артефакты загружаются, но не являются runtime-ready

`best_model.joblib`, `catboost_regressor.joblib` и `linear_regression_baseline.joblib` имеют legacy feature config и implicit `log1p` transform. Loader их поддерживает, но API readiness требует active RUB model. Использовать старые артефакты как runtime модель нельзя без отдельного readiness manifest и проверки base currency.

## `score` можно неправильно принять за ML score

`score` в `valuations` пересчитывается SQL-запросом по позиции объекта в общем рейтинге `undervaluation_percent`. Это не вероятность, не confidence и не CatBoost score.
