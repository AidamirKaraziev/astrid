---
tags: [atlas, architecture]
date: 2026-05-16
---

# Архитектура MVP monolith async (2026-05-16)

Заменяет черновик [[архитектура проекта Astra на старте scaffold]] как актуальное описание.

## Диаграмма

```
Telegram ──► aiogram handlers ──► services ──► SQLAlchemy async ──► PostgreSQL
                    │                              ▲
FastAPI REST /v1 ───┘                              │
                    └──► Redis (FSM)               │
Scheduler (09:00 TZ) ──► bot.send_message ────────┘
```

## Модули (`src/astra/`)

| Модуль | Ответственность |
|--------|-----------------|
| `users` + `profiles` | User, Profile, точность 33/66/100% |
| `predictions` | Предсказания по дням |
| `points` | Баллы, ledger |
| `referrals` | Коды, связи, награды |
| `services/` | Use cases (без логики в handlers) |
| `telegram/` | FSM, keyboards |
| `notifications/` | Scheduler |

## Стек

[[стек Python 3.12 uv и FastAPI]] + aiogram 3, asyncpg, Alembic, Redis, Docker.

## API

- `GET /health`
- `/v1/users|predictions|points|referrals` — API-first для Mini App/Web
- `POST /v1/telegram/webhook` — prod

## Конфиг (.env)

`TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `TELEGRAM_MODE=polling|webhook`.

## Связи

- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
- [[идентификация через telegram_id без fastapi-users в MVP]]
- [[деплой пока не настроен]]
