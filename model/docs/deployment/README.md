# Деплой

Этот раздел описывает локальный Docker stack и runtime configuration.

## Страницы

- [Docker](docker.md) — compose services, Dockerfiles и healthchecks.
- [Runtime config](runtime-config.md) — переменные окружения API, БД, UI и geocode.

## CI/CD

Workflow `.github/workflows/ghcr.yml` собирает контейнеры через явный matrix. Сейчас matrix содержит API image:

- module: `api`
- dockerfile: `apps/api/Dockerfile`
- context: `.`

Для нового контейнеризуемого модуля нужно добавить запись в `matrix.include` и при необходимости расширить `on.push.paths`.
