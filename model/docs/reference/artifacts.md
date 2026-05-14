# Артефакты

Source of truth: [`ml/model/persistence.py`](../../ml/model/persistence.py), [`ml/model/readiness.py`](../../ml/model/readiness.py), [`ml/model/russia2021_training.py`](../../ml/model/russia2021_training.py), [`ml/artifacts`](../../ml/artifacts).

## Runtime артефакты

| Файл | Назначение | Runtime статус |
| --- | --- | --- |
| `ml/artifacts/model_readiness.json` | Manifest активной модели | используется API |
| `ml/artifacts/best_model_russia2021.joblib` | Активный Russia 2021 CatBoost bundle | используется API через manifest |
| `ml/artifacts/best_model.joblib` | Legacy best model | поддерживается loader, не active runtime |
| `ml/artifacts/catboost_regressor.joblib` | Legacy CatBoost artifact | поддерживается loader, не active runtime |
| `ml/artifacts/linear_regression_baseline.joblib` | Legacy baseline artifact | поддерживается loader, не active runtime |
| `ml/artifacts/russia2021_prepared/` | Prepared CatBoost pools | training/debug artifact, не runtime API |

## Readiness manifest

`model_readiness.json` нужен, чтобы API не загружал случайный `joblib`. Manifest содержит:

- `status`: должен быть `ready` или `active`;
- `active_model_path`: путь к runtime bundle;
- `active_model_name`;
- `base_currency`: для active API должна быть `RUB`;
- `metrics`;
- `metadata`;
- `market_bounds`;
- `readiness_checks`.

Если `MODEL_PATH` задан явно, он должен совпасть с `active_model_path` из manifest.

## Схема bundle

`save_model_bundle` пишет словарь:

| Ключ | Значение |
| --- | --- |
| `artifact_schema_version` | версия bundle schema, сейчас `2` для новых артефактов |
| `model_name` | имя модели |
| `model` | сериализованный estimator |
| `feature_config` | source of truth для model frame |
| `metrics` | validation metrics |
| `created_at` | время сохранения |
| `target_column` | target column |
| `log_target` | legacy flag |
| `target_transform` | `identity`, `log1p` или `log` |
| `base_currency` | валюта артефакта |
| `metadata` | dataset, feature columns, prediction target, train rows и др. |

Loader поддерживает старые unversioned artifacts. Если `target_transform` отсутствует, он выводится из `log_target`: `log1p` для `true`, `identity` для `false`.

## Факты об active bundle

Текущий `best_model_russia2021.joblib`:

- model class: `catboost.core.CatBoostRegressor`;
- model name: `catboost_regressor_russia2021`;
- target column: `price`;
- target transform: `log`;
- base currency: `RUB`;
- train rows: `4377801`;
- validation rows: `1094263`;
- dataset source: `daniilakk/Russia_Real_Estate_2021:train`;
- feature columns: см. [model-inputs.md](model-inputs.md).

Важно: market bounds и category values лежат в readiness manifest, а не в самом active `joblib`.

## Prepared pools

`ml/artifacts/russia2021_prepared` содержит:

- `train_pool.csv`
- `valid_pool.csv`
- `columns.cd`

Это файлы для CatBoost pool training. Они не должны использоваться API runtime.

Текущий prepared pool был полезен для аудита, потому что показал потенциальный categorical skew: сохранённые категории выглядят как числовые коды, тогда как текущий runtime код нормализует категории в текстовые каноны.

## Training reports

`ml/reports` содержит legacy и Russia 2021 отчёты:

- `russia2021_training_report.json`;
- `russia2021_segment_metrics_report.json`, если был сгенерирован текущим pipeline;
- `russia2021_market_bounds.json`, если был сгенерирован текущим pipeline;
- legacy reports: `dataset_summary.json`, `qc_summary.json`, `model_comparison.csv`, validation reports, feature importance, shortlist CSV.

Новые training runs должны сохранять отчёты в `ml/reports`, а runtime artifact — в `ml/artifacts`.
