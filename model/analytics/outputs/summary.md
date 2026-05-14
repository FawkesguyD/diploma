# Аналитический отчет

## Источник данных

- Источник истины: `normalized_listings.normalized_payload после apps.normalization.service.normalize_raw_listing`.
- Данные читаются из БД через `shared.db.session` и ORM-модели `NormalizedListing`, `Listing`, `Valuation`.
- Сырой CSV в аналитическом контуре не используется.

## Профиль датасета

- Строк в выгрузке: 32.
- Train-eligible строк: 32.
- Лимит EDA: 200000.
- Топ районов на графике: 20.

## Цены

- Строк с положительной ценой: 32.
- Средняя цена: 171 300 613 RUB.
- Медианная цена: 159 226 003 RUB.
- Асимметрия исходной цены: 1.4900.
- Асимметрия log(price): 0.7514.

## Качество модели

- Источник модели: `readiness:/Users/daniel/Projects/ДИПЛОМ/model/ml/artifacts/model_readiness.json`.
- Оценено строк: 32.
- Пропущено inference validation: 0.
- MAE: 162 232 407 RUB.
- RMSE: 170 146 432 RUB.
- MAPE: 0.9438.
- R²: -9.8528.

### Метрики из артефакта модели

- rmse_log: 0.2962
- mae_price: 936 298
- rmse_price: 13 287 811
- mape_price: 4.5790
- r2_price: 0.1811

## Сгенерированные файлы

- `dataset_numeric_distributions.png`
- `dataset_numeric_boxplots.png`
- `dataset_price_m2_by_rooms_violin.png`
- `dataset_numeric_correlation.png`
- `dataset_top_categories.png`
- `price_distribution_raw_log.png`
- `price_qq_raw_log.png`
- `district_top_counts.png`
- `dataset_profile.json`
- `model_predicted_vs_actual.png`
- `model_residuals.png`
- `model_error_distribution.png`
- `metrics.json`

## Ограничения

- Если в `normalized_listings` нет явной валидационной или тестовой выборки, графики качества считаются на текущих нормализованных строках БД с целевой ценой.
- Обратное геокодирование выключено по умолчанию, чтобы не создавать сетевые вызовы и нагрузку на провайдера.
- Для районов используется `district`; если он пустой, резервная группа строится по `region`.
