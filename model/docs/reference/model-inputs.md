# Входной контракт модели

Эта страница описывает фактический входной контракт активной runtime модели. Source of truth: [`ml/artifacts/best_model_russia2021.joblib`](../../ml/artifacts/best_model_russia2021.joblib), [`ml/artifacts/model_readiness.json`](../../ml/artifacts/model_readiness.json), [`ml/model/feature_schema.py`](../../ml/model/feature_schema.py), [`ml/model/normalization.py`](../../ml/model/normalization.py), [`ml/model/inference_validation.py`](../../ml/model/inference_validation.py), [`ml/model/inference.py`](../../ml/model/inference.py).

## Кратко

Активная модель — CatBoost для Russia 2021, работающая в RUB. Она ожидает фиксированный frame из 18 колонок. API при этом принимает более широкий payload: часть полей используется только для postprocessing, часть является алиасами, часть игнорируется активной моделью.

Минимальный практический payload для прямого `/predict`:

```json
{
  "object_features": {
    "rooms": 2,
    "area": 50,
    "kitchen_area": 8,
    "level": 3,
    "levels": 9,
    "building_type": "panel",
    "object_type": "secondary",
    "region": "9654",
    "latitude": 55.75,
    "longitude": 37.61,
    "listing_price": 6500000,
    "listing_currency": "RUB"
  },
  "output_currency": "RUB",
  "include_explanation": true
}
```

`listing_price` можно не передавать, но тогда `delta_abs` и `delta_pct` будут `null` в direct inference.

## Реально используемые признаки модели

Активный CatBoost ожидает такие колонки в указанном порядке:

| Поле | Тип | Как получается | Обязательность на API | Поведение при отсутствии |
| --- | --- | --- | --- | --- |
| `rooms` | numeric | вход или DB | желательно | warning; CatBoost получает `NaN`, кроме studio-нормализации для `0` |
| `area` | numeric | вход или alias `total_area_m2` | обязательно | ошибка: нужна общая площадь |
| `kitchen_area` | numeric | вход или alias `kitchen_area_m2` | желательно | warning; `kitchen_ratio = NaN` |
| `level` | numeric | вход или alias `floor` | желательно | warning; floor-derived признаки становятся `NaN` |
| `levels` | numeric | вход или alias `total_floors` | желательно | warning; floor-derived признаки становятся `NaN` |
| `latitude` | numeric | вход или alias `geo_lat` | желательно | warning; `has_coordinates = 0` |
| `longitude` | numeric | вход или alias `geo_lon` | желательно | warning; `has_coordinates = 0` |
| `is_studio` | derived numeric | вычисляется из `rooms <= 0` | не передавать | пересчитывается, входное значение игнорируется |
| `area_per_room` | derived numeric | `area / rooms` | не передавать | пересчитывается |
| `floor_ratio` | derived numeric | `level / levels` | не передавать | пересчитывается |
| `is_top_floor` | derived numeric | `level == levels` | не передавать | пересчитывается |
| `is_first_floor` | derived numeric | `level == 1` | не передавать | пересчитывается |
| `kitchen_ratio` | derived numeric | `kitchen_area / area` | не передавать | пересчитывается |
| `rooms_density` | derived numeric | `rooms / area` | не передавать | пересчитывается |
| `has_coordinates` | derived numeric | `latitude` и `longitude` заполнены | не передавать | пересчитывается |
| `building_type` | categorical | вход или DB | желательно | warning; CatBoost получает `missing` |
| `object_type` | categorical | вход | желательно | warning; CatBoost получает `missing` |
| `region` | categorical | вход | желательно | warning; CatBoost получает `missing` |

Derived поля можно передать технически, но `create_model_features` пересчитает их из базовых полей. Не используйте их как ручной override.

## Все поля, которые может увидеть inference

| Поле | Алиасы | Источник | Тип | ML feature | Что делает runtime |
| --- | --- | --- | --- | --- | --- |
| `area` | `total_area_m2` | direct API, DB `Listing.area`, нормализация | numeric | да | нормализуется в `area`; нужна для модели и для расчёта price/m² |
| `total_area_m2` | `area` | legacy/API | numeric | только legacy bundle | для активной модели копируется в `area` |
| `kitchen_area` | `kitchen_area_m2` | direct API, normalization | numeric | да | участвует напрямую и в `kitchen_ratio` |
| `kitchen_area_m2` | `kitchen_area` | DB `Listing.kitchen_area_m2`, legacy/API | numeric | legacy bundle | для активной модели копируется в `kitchen_area` |
| `level` | `floor` | direct API, normalization | numeric | да | участвует напрямую и в floor-derived признаках |
| `floor` | `level` | DB `Listing.floor`, legacy/API | numeric | legacy bundle | для активной модели копируется в `level` |
| `levels` | `total_floors` | direct API, normalization | numeric | да | участвует напрямую и в floor-derived признаках |
| `total_floors` | `levels` | DB `Listing.total_floors`, legacy/API | numeric | legacy bundle | для активной модели копируется в `levels` |
| `rooms` | нет | direct API, DB, normalization | numeric | да | валидируется и используется для studio/ratio признаков |
| `latitude` | `geo_lat` | direct API, DB, geocode/normalization | numeric | да | валидируется по границам РФ |
| `longitude` | `geo_lon` | direct API, DB, geocode/normalization | numeric | да | валидируется по границам РФ |
| `geo_lat` | `latitude` | Russia2021/source payload | numeric | alias | копируется в `latitude` |
| `geo_lon` | `longitude` | Russia2021/source payload | numeric | alias | копируется в `longitude` |
| `building_type` | нет | direct API, DB, normalization | categorical | да | нормализуется по справочнику; неизвестные значения дают ошибку |
| `object_type` | нет | direct API, normalization | categorical | да | нормализуется по справочнику; в DB-backed scoring часто отсутствует |
| `region` | нет | direct API, normalization | categorical | да | приводится к строковому коду; код должен быть в train pool active model |
| `listing_price` | частично `price` | direct API, DB | service-only | нет | используется для `delta_abs` и `delta_pct` |
| `price` | частично `listing_price` | Russia2021 target, direct API | service-only на inference | нет | для активного bundle может быть fallback для listing price, если `listing_price` нет |
| `price_usd` | legacy target | legacy artifacts | legacy/service-only | нет в активной модели | для активной модели не является listing price fallback |
| `listing_currency` | нет | direct API, DB | service-only | нет | отсутствует => `RUB`; любое не-RUB значение отклоняется |
| `listing_id` | нет | direct API, DB | service-only | нет | возвращается в batch/DB flow, не влияет на prediction |
| `input_index` | нет | batch API | service-only | нет | добавляется API для восстановления исходного порядка после ранжирования |
| `output_currency` | нет | request envelope | service-only | нет | API принимает только `"RUB"` |
| `fx_rate` | нет | request/query | service-only | нет | должен быть положительным, но расчёт валют отключён и значение игнорируется |
| `include_explanation` | нет | `/predict` | service-only | нет | включает SHAP/fallback explanation |
| `include_explanations` | нет | `/predict/batch` | service-only | нет | включает explanations для каждого объекта |
| `rank_by_undervaluation` | нет | `/predict/batch` | service-only | нет | сортирует batch по `delta_pct`, затем `delta_abs_rub` |

Поля вроде `district`, `living_area_m2`, `ceiling_height`, `year_built`, `photo_count`, `seller_type`, `condition`, `heating`, `balcony`, `parking` и похожие сохраняются для legacy artifacts и DB/UI, но активная Russia 2021 модель их не использует.

## Допустимые значения и ограничения

### Числовые поля

| Поле | Фактически допустимо | Warning | Ошибка |
| --- | --- | --- | --- |
| `area` | `10 <= area <= 500` | `10 <= area < 20` | отсутствует, `<= 0`, `< 10`, `> 500` |
| `kitchen_area` | `0 <= kitchen_area <= area` | отсутствует; `kitchen_area / area > 0.55` | `< 0`, `> area` |
| `rooms` | `0..10`, дополнительно физически согласовано с площадью | отсутствует | `< 0`, `> 10`, слишком много комнат для площади (`rooms > max(1, floor(area / 8))`) |
| `level` | `1..100` | отсутствует | `< 1`, `> 100`, `level > levels` |
| `levels` | `1..100` | отсутствует | `< 1`, `> 100` |
| `latitude` | `41..82` | отсутствует или заполнена без longitude | вне диапазона РФ |
| `longitude` | `19..180` | отсутствует или заполнена без latitude | вне диапазона РФ |
| `listing_price` | любое конечное число или `null` | нет | строка, которую нельзя привести к `float`; non-RUB currency |

Нечисловые значения базовых numeric features обычно превращаются в `NaN` на этапе `pd.to_numeric(errors="coerce")`, но validation для критичных полей может раньше вернуть ошибку.

### Студии и `rooms`

`create_model_features` считает `rooms <= 0` студией, ставит `is_studio = 1` и заменяет `rooms` на `1`. Но runtime validation отклоняет отрицательные комнаты. Поэтому для прямого API используйте `rooms = 0`, а не `rooms = -1`.

### Категориальные поля

`building_type` принимает коды и текстовые варианты:

| Вход | Канон |
| --- | --- |
| `0`, `unknown`, `dont_know` | `unknown` |
| `1`, `other` | `other` |
| `2`, `panel`, `панель`, `панельный` | `panel` |
| `3`, `monolith`, `monolithic`, `монолит`, `монолитный` | `monolith` |
| `4`, `brick`, `кирпич`, `кирпичный` | `brick` |
| `5`, `block`, `blocky`, `блок`, `блочный` | `block` |
| `6`, `wood`, `wooden`, `дерево`, `деревянный` | `wooden` |
| `missing` | `missing` |

`object_type` принимает:

| Вход | Канон |
| --- | --- |
| `0`, `1`, `secondary`, `resale`, `old`, `вторичка`, `вторичный` | `secondary` |
| `2`, `11`, `new`, `newbuilding`, `new_building`, `новостройка`, `новый` | `new` |
| `unknown` | `unknown` |
| `missing` | `missing` |

Любое неизвестное значение `building_type` или `object_type` приводит к ошибке validation. Значения `unknown` и `missing` допустимы, но снижают confidence.

`region` приводится к строке. Значения вида `9654.0` нормализуются в `9654`. Если `region` указан, он должен входить в список регионов active train pool из readiness manifest. Текущий список:

```text
3, 69, 81, 821, 1010, 1491, 1901, 2072, 2328, 2359, 2484, 2528, 2594,
2604, 2661, 2722, 2806, 2814, 2843, 2860, 2871, 2880, 2885, 2900,
2922, 3019, 3106, 3153, 3230, 3446, 3870, 3991, 4007, 4086, 4189,
4240, 4249, 4374, 4417, 4695, 4963, 4982, 5143, 5178, 5241, 5282,
5368, 5520, 5703, 5736, 5789, 5794, 5952, 5993, 6171, 6309, 6543,
6817, 6937, 7121, 7793, 7873, 7896, 7929, 8090, 8509, 8640, 8894,
9579, 9648, 9654, 10160, 10201, 10582, 11171, 11416, 11991, 13098,
13913, 13919, 14368, 14880, 16705, 61888
```

## Различия между потоками

### Прямой `/predict`

- Вход: один `object_features`.
- Любая validation error превращается в HTTP 400.
- Extra keys сохраняются в исходном dict, но не попадают в model frame, если их нет в `feature_config`.
- `price_outputs` всегда содержит только ключ `RUB`.

### `/predict/batch`

- Вход: список объектов `objects`, минимум 1.
- API добавляет `input_index`.
- Если один объект невалиден, endpoint возвращает HTTP 400 для всего batch.
- При `rank_by_undervaluation = true` результаты сортируются по `delta_pct`, затем `delta_abs_rub`; исходный порядок можно восстановить по `input_index`.

### DB-backed scoring и backfill

- Поток используется в `/opportunities`, `/shortlist` и `services/data_migrator/bootstrap.py`.
- Источник полей — таблица `listings`.
- `build_listing_model_payload` копирует только те поля, которые есть в active `feature_config`.
- Невалидные строки не валят endpoint, а пропускаются с log warning.
- В текущей схеме `listings` нет `object_type` и `region`, поэтому DB-backed scoring часто работает с `missing` категориями и lower confidence.

## Безопасно не передавать

Можно не передавать:

- `listing_price`: prediction будет рассчитан, но delta не будет рассчитана.
- `building_type`, `object_type`, `region`: prediction возможен, но появятся warnings и ниже confidence.
- `latitude`, `longitude`: prediction возможен, но `has_coordinates = 0` и confidence ниже.
- `kitchen_area`, `rooms`, `level`, `levels`: prediction может быть возможен, но качество ниже; `area` остаётся обязательной.

## Критично для качества

Наиболее важные поля для поддерживаемого runtime контракта:

- `area`
- `rooms`
- `kitchen_area`
- `level`
- `levels`
- `region`
- `object_type`
- `building_type`
- `latitude` и `longitude`
- `listing_price` для корректного undervaluation signal, но не для самой ML-оценки

## Известные проблемы контракта

- `rooms = -1` допустим в training preprocessing как studio marker, но не проходит runtime validation.
- `price`, `listing_price` и `price_usd` имеют исторически разную семантику. Для runtime API используйте `listing_price`.
- Сохранённый prepared train pool содержит числовые категории, а текущий runtime нормализует категории в текстовые значения.
- Активная модель не использует многие поля, которые всё ещё есть в DB и UI для legacy/продуктового контекста.
