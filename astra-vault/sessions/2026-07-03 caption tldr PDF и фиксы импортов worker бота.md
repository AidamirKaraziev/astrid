---
tags: [session, compatibility, telegram, worker, debugging]
date: 2026-07-03
---

# Caption tldr при отправке PDF совместимости + фиксы импортов

Связано: [[пайплайн совместимости промпт LLM PDF worker]] · [[Split Contract LLM и Pydantic для совместимости]]

## Сделано

### Caption к PDF в Telegram
- `format_compatibility_pdf_caption()` в `compatibility_service.py`: берёт `tldr` из `report.llm_output`, футер `💕 {report.title}`.
- Формат: краткий итог (2–3 предложения) → пустая строка → заголовок пары.
- Fallback без `llm_output`: только футер (как раньше).
- Обрезка при лимите Telegram caption 1024 символа.
- Подключено в `deliver_compatibility_report` (автоотправка и resend из «Мои разборы»).
- Тесты: `tests/test_compatibility_service.py` (3 кейса).

### Багфиксы prod (после деплоя observability-ветки)

1. **API / FSM совместимости** — `NameError: name 'date' is not defined` в `telegram/handlers/compatibility.py` (использовался `date.fromisoformat`, импортирован был только `datetime`). Падало на подтверждении данных и вводе времени рождения.

2. **Worker** — `NameError: name 'dispatch_task' is not defined` в `workers/consumer.py`: вызов без `from astra.workers.handlers import dispatch_task`. Все задачи RabbitMQ (prediction + compatibility) не обрабатывались.

→ [[после рефакторинга забытые импорты date и dispatch_task]]

## Не сделано / на потом

- Коммит и деплой на deadtiger (если ещё не выкатил).
- E2E: новый разбор → PDF с tldr в caption.
- Split Contract LLM — по-прежнему в приоритете из [[текущие приоритеты]].

## Действия на сервере

```bash
docker compose up -d --build api worker
```

Проверить: заказ совместимости до PDF; в логах worker нет `dispatch_task` / `date` NameError.
