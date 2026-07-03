---
tags: [decision, observability, logging]
date: 2026-07-03
---

# correlation_id propagation через RabbitMQ и Telegram

## Поток

1. **Telegram update** → `correlation_id = upd-{update_id}` в `TelegramObservabilityMiddleware`.
2. **Publish** → берётся из contextvars или генерируется `task-{uuid}`; пишется в `TaskMessage.correlation_id` и header `x-correlation-id`.
3. **Worker consume** → из `TaskMessage` или AMQP header → `bound_context(correlation_id=…)`.
4. **HTTP** → `X-Correlation-ID` / `X-Request-ID` или `http-{uuid}`.

## Схема

`TaskMessage.correlation_id: str | None` — опционально для обратной совместимости старых сообщений в очереди.

## Связи

- [[structured logging structlog и event taxonomy Astra]]
