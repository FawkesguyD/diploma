# Дипломный проект — АИС с интеллектуальным анализом и визуализацией данных

Автоматизированная информационная система: парсинг Telegram/новостных каналов и площадок недвижимости, NLP-анализ потоков, оценка объектов недвижимости, дашборды. Полный контекст — [CONTEXT.md](CONTEXT.md).

## Запуск

```bash
cp .env.example .env
task up           # либо: docker compose up -d --build
task ps
task logs
```

Остановка: `task down`. Полный рестарт с очисткой данных: `task fresh`.

## Доступы (по умолчанию)

| Сервис      | URL                                         | Логин / пароль из `.env`                  |
|-------------|---------------------------------------------|-------------------------------------------|
| Traefik UI  | http://localhost:8080                        | без аутентификации (dev)                  |
| API gateway | http://localhost:80                          | через `/api/*`                            |
| Postgres    | localhost:5432                               | `POSTGRES_USER` / `POSTGRES_PASSWORD`     |
| Mongo       | localhost:27017                              | `MONGO_INITDB_ROOT_USERNAME` / `..._PASSWORD` |
| ClickHouse  | http://localhost:8123                        | `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` |
| RabbitMQ UI | http://localhost:15672                       | `RABBITMQ_DEFAULT_USER` / `..._PASS`      |
| Kafka       | localhost:9092                               | PLAINTEXT                                  |
| MinIO API   | http://localhost:9100                        | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| MinIO UI    | http://localhost:9101                        | те же                                      |

## Документация

- [CONTEXT.md](CONTEXT.md) — цели и ограничения проекта
- [docs/design/README.md](docs/design/README.md) — индекс design-документов
- [docs/design/databases/](docs/design/databases) — схемы Postgres / Mongo / ClickHouse
- [docs/design/messaging/](docs/design/messaging) — RabbitMQ + Kafka контракты
- [docs/design/api/](docs/design/api) — REST API и маршрутизация шлюза

## Структура

```
docker-compose.yml      # единый compose для всех сервисов
taskfile.yml            # ярлыки команд
.env.example            # шаблон конфигурации
infra/                  # init-скрипты и конфиги инфраструктуры
  postgres/init/        # bootstrap-схемы core/ops
  mongo/init/           # индексы коллекций
  clickhouse/init/      # таблицы events_* + MV
  rabbitmq/             # Dockerfile с плагином + definitions.json
  minio/                # init bucket=models
services/               # бэкенд-сервисы (добавят отдельные агенты)
```
