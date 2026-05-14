# Архитектура

Этот раздел отвечает на вопрос, как связаны API, ML, DB, UI и служебные модули.

## Страницы

- [Структура репозитория](repository-structure.md) — зоны ответственности каталогов и compatibility shims.
- [API -> ML flow](api-ml-flow.md) — путь данных для direct prediction, batch и DB-backed scoring.
- [Inference lifecycle](inference-lifecycle.md) — что происходит внутри inference от загрузки bundle до ranking.
- [Диаграммы](diagrams/README.md) — PlantUML/C4 исходники и сгенерированные изображения.

## Ключевой принцип

Внешний контракт API, UI и DB не должен зависеть от внутренних перестановок ML-кода. Поэтому реальные source-of-truth точки зафиксированы отдельно в [audit-summary.md](../reference/audit-summary.md), а модельный контракт вынесен в [model-inputs.md](../reference/model-inputs.md).
