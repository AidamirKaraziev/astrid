---
tags: [decision, auth]
date: 2026-05-16
---

# Идентификация через telegram_id без fastapi-users в MVP

## Контекст

Нужна максимально простая регистрация в Telegram-боте; в будущем — Web/mobile с JWT.

## Решение

- Пользователь = запись в `users` с уникальным `telegram_id`.
- Пароли и email не требуются в MVP.
- REST API временно принимает `user_id` в path (`/v1/users/me/{user_id}`).
- **fastapi-users** — когда появится email/пароль на сайте.

## Последствия

- Проще онбординг, меньше зависимостей.
- API не защищён для внешних клиентов до JWT — ок для MVP, закрыть перед публичным Web.

## Связи

- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
- [[2026-05-16 discovery и MVP scaffold async telegram бота]]
