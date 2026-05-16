---
tags: [decision, architecture]
date: 2026-05-16
---

# Monolith FastAPI + aiogram без RabbitMQ в MVP

## Контекст

В spec указаны Postgres, Redis, RabbitMQ, microservices «если нужно».

## Решение

- **Один процесс:** FastAPI + aiogram polling/webhook + notification scheduler.
- **Redis:** FSM aiogram, кэш в будущем.
- **RabbitMQ:** не подключаем в MVP; рассылка через asyncio worker раз в минуту.
- Модули (`users/`, `predictions/`, `services/`) — границы для будущего выделения сервисов.

## Trade-offs

| Плюс | Минус |
|------|-------|
| Быстрый MVP, один deploy | Scheduler не переживёт горизонтальное масштабирование без доработки |
| Меньше ops | Тяжёлые AI-задачи позже потребуют очереди |

## Когда пересмотреть

- >5k DAU или платные async-разборы → ARQ/Celery/RabbitMQ.
- Несколько реплик API → вынести scheduler + distributed lock (Redis).

## Связи

- [[scheduler рассылки в том же процессе что API]]
