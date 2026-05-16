---
tags: [decision, notifications]
date: 2026-05-16
---

# Scheduler рассылки в том же процессе что API

## Контекст

Ежедневные предсказания в 09:00 по локальному TZ пользователя (город → timezone).

## Решение

- Фоновая задача в `lifespan` FastAPI: каждые 60 с проверка пользователей с `onboarding_completed`.
- Идемпотентность: не слать, если `predictions.sent_at` уже установлен на эту локальную дату.
- Отправка через общий экземпляр `aiogram.Bot`.

## Альтернативы (отложены)

- Cron + отдельный worker
- Temporal

## Связи

- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
