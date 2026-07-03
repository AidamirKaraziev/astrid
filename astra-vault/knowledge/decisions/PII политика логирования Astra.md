---
tags: [decision, observability, security]
date: 2026-07-03
---

# PII политика логирования Astra

## Не логировать

- `TELEGRAM_BOT_TOKEN`, API keys, пароли
- Полные тексты сообщений пользователей
- Промпты и ответы LLM (только метаданные: provider, model, duration_ms, reason)
- Точные координаты геолокации

## Разрешено

- `user_id`, `telegram_id`, `report_id`, `update_id`
- `correlation_id`, `task_type`, коды ошибок (`validation_orbs`, `timeout`)
- Имена городов (без точных координат)

## Реализация

Processor `sanitize_pii` в `astra/core/observability/processors.py` — маскирует ключи, содержащие token/secret/password/api_key/prompt/completion.

## Связи

- [[structured logging structlog и event taxonomy Astra]]
