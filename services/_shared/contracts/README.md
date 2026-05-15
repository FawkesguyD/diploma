# aisi-contracts

Общие Pydantic-модели сообщений между сервисами АИС.

Источник правды по контрактам — `/Users/daniel/Projects/ДИПЛОМ/docs/design/messaging/README.md`.

## Установка (editable)

```bash
pip install -e services/_shared/contracts
```

## Содержание

- `aisi_contracts.envelope` — общий конверт `Envelope` для RabbitMQ и Kafka (`schema_version`, `message_id`, `correlation_id`, `issued_at`, `payload`).
- `aisi_contracts.realestate` — payload-модели очередей `realestate.score`, `realestate.rank`, а также `ScoreResult` для внутренней передачи.
- `aisi_contracts.metrics` — payload Kafka-топиков. Сейчас реализован `PriceMetric` (`metrics.prices`). `MessageMetric` (`metrics.messages`) — TODO для nlp-агента.
