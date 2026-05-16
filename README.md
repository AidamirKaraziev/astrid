# Astra

Telegram-бот с ежедневными персональными предсказаниями. Async-стек: **FastAPI**, **aiogram 3**, **SQLAlchemy 2**, **PostgreSQL**, **Redis**.

## Быстрый старт

### 1. Инфраструктура

```bash
docker compose up -d postgres redis
```

### 2. Окружение

```bash
cp .env.example .env
# Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_BOT_USERNAME в .env
```

### 3. Зависимости и миграции

```bash
uv sync --all-extras
uv run alembic upgrade head
```

### 4. Запуск API + бота (polling)

```bash
uv run uvicorn astra.main:app --reload --app-dir src
```

Бот и планировщик уведомлений (09:00 по TZ города) стартуют вместе с приложением.

## Структура

```
src/astra/
├── main.py              # FastAPI + lifespan (бот, scheduler)
├── core/                # config, cities → timezone
├── db/                  # SQLAlchemy session
├── users/               # User, Profile
├── predictions/
├── points/
├── referrals/
├── notifications/       # scheduler
├── services/            # бизнес-логика
└── telegram/            # aiogram handlers
```

## API (MVP)

| Endpoint | Описание |
|----------|----------|
| `GET /health` | healthcheck |
| `GET /v1/users/me/{user_id}` | профиль (до JWT) |
| `GET /v1/predictions/today/{user_id}` | предсказание на сегодня |
| `GET /v1/points/balance/{user_id}` | баллы и streak |
| `GET /v1/referrals/stats/{user_id}` | реферальная ссылка |
| `POST /v1/telegram/webhook` | webhook (prod) |

## Тесты

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
uv run pytest -v
```

## Docker (полный стек)

```bash
docker compose up --build
```
