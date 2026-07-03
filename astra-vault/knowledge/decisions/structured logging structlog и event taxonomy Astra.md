---
tags: [decision, observability, logging]
date: 2026-07-03
---

# Structured logging structlog и event taxonomy Astra

## Решение

- Единый пакет `astra/core/observability/`: structlog, contextvars, middleware.
- События — стабильные идентификаторы `Event` (`task.completed`, `prediction.sent`, …), не свободный текст.
- Контекст в каждой строке: `correlation_id`, `user_id`, `report_id`, `task_type`, `service`.
- `correlation_id` передаётся через `TaskMessage` и AMQP header `x-correlation-id`.
- Prod: `LOG_FORMAT=json`; dev: `LOG_FORMAT=plain` (ConsoleRenderer).
- PII: processor `sanitize_pii` маскирует token/secret/api_key/prompt/completion.

## Entry points

| Точка входа | Middleware |
|-------------|------------|
| FastAPI | `HttpObservabilityMiddleware` |
| aiogram | `TelegramObservabilityMiddleware` |
| RabbitMQ worker | `run_task_with_observability` |

## Инициализация

```python
configure_observability(settings)  # api: create_app; worker: run()
```

## Следующие этапы

- OpenTelemetry traces + propagation traceparent в RabbitMQ
- Loki/Grafana в docker-compose profile `observability`
- Миграция оставшихся модулей с `logging.getLogger` на `get_logger`

## Связи

- [[Sentry environment local dev prod и service api worker]]
- [[correlation_id propagation через RabbitMQ и Telegram]]
- [[PII политика логирования Astra]]
