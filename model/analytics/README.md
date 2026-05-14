# Аналитика нормализованного датасета и качества модели

Этот каталог содержит отдельный аналитический контур проекта. Он читает данные из нормализованного слоя БД, строит EDA-графики, аналитику цен, топ районов и графики качества inference-модели.

## Источник данных

Источник истины для датасета: таблица `normalized_listings`, поле `normalized_payload`.

Данные попадают туда через текущий pipeline:

1. `services/data_migrator/importer.py` читает исходные строки.
2. `apps.normalization.service.normalize_raw_listing()` приводит поля к runtime/model-схеме, применяет алиасы и проверку качества входа.
3. Мигратор сохраняет результат в `normalized_listings`.
4. Таблицы `listings` и `valuations` используются только как связка для отображаемых полей, районов и уже сохраненных оценок.

Сырой CSV не используется аналитикой.

## Подключение к БД

Используется тот же паттерн, что и в проекте:

- `DATABASE_URL`, если переменная задана;
- иначе default из `shared.db.session`.

Пример:

```bash
DATABASE_URL=postgresql+psycopg://realestate:realestate@localhost:5432/realestate \
python analytics/generate_report.py
```

## Запуск

Основной интерфейс без ноутбуков:

```bash
python analytics/generate_report.py
```

Полезные параметры:

```bash
python analytics/generate_report.py --max-rows 50000 --eval-max-rows 3000 --top-districts 20
python analytics/generate_report.py --skip-model-quality
python analytics/generate_report.py --enable-reverse-geocoding
```

Обратное геокодирование по умолчанию выключено. Если включить `--enable-reverse-geocoding`, используется существующий `apps.geocode.service.GeocodingService`, но только для строк с пустым районом и координатами. Лимит задается через `ANALYTICS_GEOCODE_LIMIT`.

## Сравнение valuation-подходов

Контур сравнения использует отдельную PostgreSQL-таблицу `analytics_control_objects`. Она заполняется из `normalized_listings`, то есть из того же нормализованного слоя, который используется аналитикой и DB-backed training pipeline.

Создать или обновить контрольную выборку из 1000 объектов:

```bash
DATABASE_URL=postgresql+psycopg://realestate:realestate@localhost:5432/realestate \
python analytics/bootstrap_control_sample.py --sample-size 1000 --sample-seed 42
```

Скрипт выполняет `analytics/sql/control_sample.sql`, детерминированно выбирает строки по стабильному SHA-256 ключу `sample_seed + source_object_id` и перезаписывает строки выбранного seed в одной транзакции. Повторный запуск с тем же seed безопасен и дает тот же состав при неизменном source dataset.

Запустить сравнение трех подходов:

```bash
DATABASE_URL=postgresql+psycopg://realestate:realestate@localhost:5432/realestate \
python analytics/compare_valuation_approaches.py --sample-seed 42
```

Подходы:

- `price_per_meter` — хранит score `listing_price / area`; для valuation estimate использует медианную цену за м² похожего сегмента контрольной выборки без текущего объекта.
- `formula` — MVP-baseline с явными коэффициентами из `apps/analytics_service/config.py`, чтобы не создавать второй источник правды.
- `regression` — активный runtime inference pipeline через readiness manifest/joblib bundle, без переобучения модели.
- `my_model` — явный отчетный alias активной regression-модели проекта. Используется для отдельного блока показателей моей модели.

Результаты сравнения сохраняются в `analytics/reports/`:

- `control_sample_predictions.csv` — per-object результаты всех подходов.
- `control_sample_metrics.csv` — MAE, RMSE, MAPE, R² и ranking-метрики.
- `my_model_control_metrics.csv` — NDCG@10, NDCG@20, Precision@10, ProfitCapture@10, Spearman, MAE и MAPE для активной модели.
- `ranking_comparison.csv` — ранги объектов по undervaluation signals.
- `mae_rmse_mape_comparison.png` — сравнение агрегированных value-метрик.
- `predicted_vs_target_formula.png` — Formula estimate против proxy target.
- `predicted_vs_target_regression.png` — Regression estimate против proxy target.
- `predicted_vs_target_my_model.png` — estimate активной модели против proxy target.
- `error_distribution.png` — распределение ошибок.
- `ranking_comparison.png` — ranking comparison по proxy signal.
- `summary.json` и `summary.md` — краткое резюме, ограничения и metadata.

## Переменные окружения

- `DATABASE_URL` — подключение к PostgreSQL.
- `MODEL_PATH` — явный путь к joblib-артефакту.
- `MODEL_READINESS_PATH` — путь к манифесту готовности модели, по умолчанию `ml/artifacts/model_readiness.json`.
- `ANALYTICS_OUTPUT_DIR` — каталог результатов, по умолчанию `analytics/outputs`.
- `ANALYTICS_MAX_ROWS` — лимит строк для EDA, по умолчанию `200000`.
- `ANALYTICS_EVAL_MAX_ROWS` — лимит строк для inference-оценки, по умолчанию `5000`.
- `ANALYTICS_TOP_DISTRICTS` — топ-N районов, по умолчанию `20`.
- `ANALYTICS_ENABLE_REVERSE_GEOCODING` — опциональное обогащение районов через геосервис.
- `ANALYTICS_REPORTS_DIR` — каталог результатов сравнения подходов, по умолчанию `analytics/reports`.
- `ANALYTICS_CONTROL_SAMPLE_SIZE` — размер контрольной выборки, по умолчанию `1000`.
- `ANALYTICS_CONTROL_SAMPLE_SEED` — seed контрольной выборки, по умолчанию `42`.

## Результаты

Файлы сохраняются в `analytics/outputs/`:

- `dataset_numeric_distributions.png` — распределения площадей, комнат, этажей, года постройки и price per m².
- `dataset_numeric_boxplots.png` — boxplot по числовым признакам.
- `dataset_price_m2_by_rooms_violin.png` — violinplot цены за м² по комнатности.
- `dataset_numeric_correlation.png` — heatmap корреляций полезных numeric полей.
- `dataset_top_categories.png` — топ категорий.
- `district_top_counts.png` — топ районов или резервных групп.
- `price_distribution_raw_log.png` — исходная цена и `log(price)` с оценкой плотности.
- `price_qq_raw_log.png` — Q-Q график для исходной цены и `log(price)`.
- `model_predicted_vs_actual.png` — прогноз против факта с диагональю идеального попадания.
- `model_residuals.png` — график ошибок.
- `model_error_distribution.png` — распределение ошибок и абсолютной процентной ошибки.
- `dataset_profile.json` — профиль выгрузки.
- `metrics.json` — метрики качества модели и источник артефакта.
- `summary.md` — краткие выводы и ограничения.

## Ограничения

- Если в `normalized_listings` нет отдельной валидационной или тестовой выборки, качество считается на текущих нормализованных строках БД с целевой ценой. Метрики из активного артефакта дополнительно выводятся в `summary.md`.
- Район берется из нормализованных данных или из `listings.district`. Если район пустой, график использует резервную группировку по `region`.
- Обогащение районов через reverse geocoding не выполняется автоматически, чтобы не создавать сетевые вызовы и не зависеть от внешнего провайдера.
- В сравнении трех подходов нет честного transaction truth. `target_proxy_price` основан на `listing_price`, поэтому результаты нужно читать как сравнение proxy valuation/model estimate, trained on listing data, а не как доказательство рыночной цены или реальной инвестиционной доходности.
