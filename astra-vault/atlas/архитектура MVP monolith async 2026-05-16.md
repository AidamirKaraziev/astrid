---
tags: [atlas, architecture]
date: 2026-07-21
---

# Архитектура MVP monolith async (2026-05-16)

Актуализировано 2026-08-07. Два процесса: **api** (FastAPI + aiogram + scheduler) и **worker** (RabbitMQ consumer для LLM-задач).

## Диаграмма

```
Telegram ──► aiogram handlers ──► services ──► SQLAlchemy async ──► PostgreSQL
                    │                              ▲
FastAPI REST /v1 ───┘                              │
                    ├──► Redis (FSM, кэш file_id)  │
                    └──► RabbitMQ ──► worker ──► DeepSeek LLM ──► bot.send
Scheduler (09:00 TZ, в процессе api) ──► RabbitMQ (генерация) / bot.send
```

## Модули (`src/astra/`)

| Модуль | Ответственность |
|--------|-----------------|
| `users`, `places` | User, Profile, геокодинг GeoNames |
| `predictions` | ежедневные прогнозы (Astrid v4, DeepSeek) |
| `tarot` | колода 78 карт, расклады, карта дня |
| `payments` | Telegram Stars: каталог `products`/`product_prices`, снапшоты, refund |
| `compatibility` | синастрия пары, PDF-отчёт |
| `natal_report` | разбор натала (на `main`, продукт не выставлен в каталог) |
| `points`, `referrals` | баллы, ledger, реферальные коды |
| `wheel` | колесо фортуны: бесплатное вращение раз в день, платные за Stars |
| `ask` | раздел «Спроси Астрид» — вопросы к своей карте, товар на каждый |
| `support` | служба заботы: FAQ и релей обращений через админ-группу |
| `broadcasts` | рассылки: аудитория по фильтрам, ИИ-редактор, отправка воркером |
| `usage` | журнал использования продуктов, дни активности, вызовы LLM |
| `admin` | панель `/admin`: каталог, очередь, платежи, метрики, рассылки |
| `llm` | провайдеры (DeepSeek), промпты на продукт |
| `astro` | эфемериды, наталы, транзиты |
| `messaging`, `workers` | RabbitMQ publish/consume, обработчики задач |
| `telegram` | FSM, keyboards, AutoKeyboardMiddleware |
| `notifications` | scheduler рассылки (в процессе api) |
| `core` | config, observability (structlog, Sentry, OTel) |
| `services/` | use cases (без логики в handlers) |

## Стек

[[стек Python 3.12 uv и FastAPI]] + aiogram 3, asyncpg, Alembic, Redis, RabbitMQ, Docker.

## API

- `GET /health`
- `/v1/users|predictions|points|referrals` — API-first для Mini App/Web
- `POST /v1/telegram/webhook` — prod

## Конфиг (.env)

`TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `DEEPSEEK_API_KEY`, `TELEGRAM_MODE=polling|webhook`, `TELEGRAM_PROXY_URL`.

## Связи

- [[monolith FastAPI aiogram без RabbitMQ в MVP]] (частично superseded — RabbitMQ подключён)
- [[идентификация через telegram_id без fastapi-users в MVP]]
- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]
- [[таро гибридный пайплайн карты мгновенно интерпретация из worker]]
- [[пайплайн совместимости промпт LLM PDF worker]]
