---
tags: [debugging, telegram, worker, compatibility]
date: 2026-07-03
---

# После рефакторинга забытые импорты date и dispatch_task

Сессия: [[2026-07-03 caption tldr PDF и фиксы импортов worker бота]]

## Симптомы

**API (telegram.update.failed):**
```
NameError: name 'date' is not defined
```
Callback/message на шагах FSM совместимости (подтверждение, время рождения).

**Worker (asyncio task exception):**
```
NameError: name 'dispatch_task' is not defined
```
Любое сообщение из RabbitMQ — consumer падает до обработки.

## Причина

Рефакторинг observability / handlers: использование символов без импорта.

| Файл | Символ | Где вызывается |
|------|--------|----------------|
| `telegram/handlers/compatibility.py` | `date` | `date.fromisoformat` в FSM |
| `workers/consumer.py` | `dispatch_task` | `_process_message` |

## Фикс

```python
# compatibility.py
from datetime import date, datetime

# consumer.py
from astra.workers.handlers import dispatch_task
```

## Как не повторить

После выноса функций между модулями — grep по вызываемым именам и прогон импорта:

```bash
uv run python -c "from astra.workers.consumer import run_consumer"
uv run python -c "from astra.telegram.handlers.compatibility import router"
```
