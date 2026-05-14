# Диаграммы как код

В этой папке лежат текстовые исходники архитектурных диаграмм проекта в формате PlantUML. Они описывают текущее состояние MVP и должны обновляться вместе с изменением реальной структуры кода, entrypoint'ов и runtime-связей.

## Что здесь лежит

- `c4-component.puml` - C4 Component view для текущего backend/API контура и его реальных зависимостей.
- `c4-code-predict.puml` - code-level C4-style view для сценария `POST /predict` на уровне реальных модулей, функций и схем.
- `sequence-predict.puml` - sequence diagram для основного сценария предсказания через API.
- `uml-component.puml` - UML component view по основным модулям монорепозитория и их зависимостям.

## Локальный рендер

Если `plantuml` установлен локально:

```bash
plantuml docs/architecture/diagrams/*.puml
```

Docker-вариант без локальной установки:

```bash
docker run --rm -v "$PWD":/work -w /work plantuml/plantuml docs/architecture/diagrams/*.puml
```

Примечание: C4-диаграммы используют `!includeurl` из C4-PlantUML, поэтому при рендере нужен доступ к сети.

## Правила обновления

- Не добавлять в диаграммы сущности, которых нет в коде, `docker-compose.yml` или подтвержденной структуре репозитория.
- Не показывать proxy valuation как transaction-based fair market valuation.
- Разделять runtime, code-level и training/infrastructure связи; не смешивать их в одной диаграмме без явной причины.
- При изменении entrypoint'ов, endpoint'ов, ML flow, `shared/` зависимостей или compose-топологии обновлять соответствующие `.puml` файлы.
