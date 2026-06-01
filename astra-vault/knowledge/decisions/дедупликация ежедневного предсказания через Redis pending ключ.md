---
tags: [decision, rabbitmq, redis, predictions]
date: 2026-06-01
---

# Дедупликация ежедневного предсказания через Redis pending ключ

## Проблема

Повторные нажатия «🔮 Предсказание на сегодня» ставили несколько задач в RabbitMQ → несколько сообщений в Telegram.

## Почему не RabbitMQ

Брокер не знает бизнес-состояние («уже в очереди / уже в БД без sent_at»). Дедуп по `user_id` в RabbitMQ — костыль.

## Решение

- Ключ Redis: `astra:prediction:pending:{user_id}:{YYYY-MM-DD}`, TTL 15 мин, `SET NX`.
- `request_today_prediction()` — единая точка входа; при занятом ключе → `IN_PROGRESS` и текст «Почти готово…».
- Снятие ключа: после успешного `prediction.send` в worker; при ошибке generate — `clear`.

## Связи

- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
- [[2026-06-01 онбординг профиль Sentry и RabbitMQ]]
