# Архитектурные диаграммы

Источник правды по архитектуре системы. **Любое изменение архитектуры синхронизируется с этими файлами.**

## Файлы

| Файл | Уровень | Что показывает |
|---|---|---|
| [context.puml](context.puml) | C4 L1 — Context | Систему как чёрный ящик, её пользователей и внешние источники данных |
| [container.puml](container.puml) | C4 L2 — Container | Все контейнеры (сервисы, БД, брокеры) и потоки данных между ними |
| [component.puml](component.puml) | C4 L3 — Component | Внутреннее устройство каждого сервиса (компоненты и их связи) |
| [deployment.puml](deployment.puml) | Deployment | Физическое развёртывание: хост, docker-сети, порты |
| [sequence-redis-ingest.puml](sequence-redis-ingest.puml) | Sequence | Поток ingestion с Redis: rate-limit парсеров и dedup сообщений/объектов |

## Как смотреть

**В IDE:**
- VSCode: расширение `jebbs.plantuml` → `Alt+D` для предпросмотра.
- IntelliJ: встроенная поддержка `.puml` через PlantUML plugin.

**Локально (CLI):**
```bash
brew install plantuml
plantuml docs/architecture/*.puml          # → PNG рядом с .puml
plantuml -tsvg docs/architecture/*.puml    # → SVG (для диплома)
```

**Онлайн без установки:** скопировать содержимое `.puml` файла в [planttext.com](https://www.planttext.com/) или [plantuml.com/plantuml](https://www.plantuml.com/plantuml/uml).

## Правило поддержки

При изменении архитектуры (новый сервис, новая очередь, перенесли БД и т.п.):

1. Сначала правим соответствующую диаграмму.
2. Затем — код и `docker-compose.yml`.
3. Если изменение существенное — добавляем ADR в [../decisions/](../decisions/).

Диаграмма всегда отражает **текущее**, а не желаемое состояние.

## Ключевые принципы архитектуры (закреплены в плане)

- **Один хост, `docker compose`** — без k8s, без облаков.
- **Edge = Traefik** — единая точка входа, маршрутизация по префиксам.
- **RabbitMQ ≠ Kafka** — RabbitMQ для команд между сервисами, Kafka **только** для метрик (гарантия доставки, изоляция от оперативного контура).
- **Три БД по назначению**:
  - PostgreSQL — реляционные данные (пользователи, конфиги).
  - MongoDB — документные (сообщения, объявления).
  - ClickHouse — аналитика и метрики.
- **MinIO** — версионирование артефактов ML-моделей.
- **Три прикладных сервиса**: realestate, nlp-parser, metrics + frontend.
- **Redis — вспомогательный sidecar** (см. [ADR-0009](../decisions/0009-redis-auxiliary-layer.md)): дедупликация входящих сообщений/объектов и outbound rate-limit парсеров. **Не** заменяет RabbitMQ/Kafka/Mongo/ClickHouse и не хранит бизнес-данные.
