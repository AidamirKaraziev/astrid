---
tags: [session]
date: 2026-05-16
---

# Сессия: discovery и MVP scaffold async Telegram-бота

## Цель сессии

Зафиксировать продукт Astra, согласовать MVP, собрать production-ready async-каркас с Telegram-ботом.

## Продукт (зафиксировано)

- **Astra** — ежедневные персональные предсказания для RU-аудитории (в основном женщины, эзотерика/астрология).
- **Канал MVP:** только Telegram-бот; Mini App и Web — позже.
- **Монетизация MVP:** бесплатно; баллы и платные разборы — позже.
- **AI:** обязателен в продукте, в коде пока **заглушки** (шаблон + знак зодиака).
- **Цель масштаба (долгосрок):** ~100k платящих × 100₽/мес.

## MVP-функции (реализовано в коде)

| Функция | Статус |
|---------|--------|
| Онбординг (имя, дата, город) | ✅ |
| Уровни точности профиля 33/66/100% | ✅ |
| Ежедневная рассылка 09:00 по TZ города | ✅ |
| Баллы (+7/день), streak | ✅ |
| Рефералка `ref_<code>`, бонусы 50/10 | ✅ |
| REST API `/v1/*` для будущего фронта | ✅ |
| Postgres + Redis + Alembic + Docker | ✅ |
| pytest (10 тестов) | ✅ |
| CI GitHub Actions | ✅ |

## Архитектурные решения

→ [[идентификация через telegram_id без fastapi-users в MVP]]
→ [[monolith FastAPI aiogram без RabbitMQ в MVP]]
→ [[scheduler рассылки в том же процессе что API]]
→ [[MCP servers рекомендации на потом]]

## Структура репозитория (после сессии)

```
src/astra/
├── main.py              # FastAPI + lifespan (бот, scheduler)
├── core/                # config, cities→timezone
├── db/                  # async SQLAlchemy
├── users/ profiles/ predictions/ points/ referrals/
├── services/            # бизнес-логика
├── notifications/       # scheduler 09:00
└── telegram/            # aiogram 3 FSM
alembic/  tests/  docker-compose.yml
```

## Не сделано / отложено

- Подключение реального LLM (Langfuse, multi-provider).
- RAG / long-term memory.
- Оплата (карты, СБП, крипта, Telegram Payments).
- Mini App, Web/mobile.
- Деплой на prod.
- Заметка MCP в vault — создана отдельно.
- `spec/project.md` — частично заполнен пользователем, не синхронизирован полностью.

## Как запустить локально

```bash
docker compose up -d postgres redis
cp .env.example .env  # TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn astra.main:app --reload --app-dir src
```

## Следующая сессия

1. Заполнить/синхронизировать `spec/project.md` с vault.
2. Прогнать бота end-to-end с реальным токеном BotFather.
3. Подключить первый LLM-провайдер вместо заглушки.
4. Деплой staging (webhook mode).

## Связи

- [[текущие приоритеты]]
- [[архитектура MVP monolith async 2026-05-16]]
- [[продукт Astra telegram предсказания RU аудитория]]
