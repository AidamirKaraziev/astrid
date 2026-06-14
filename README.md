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

### 3.1. Справочник городов и деревень РФ (GeoNames, бесплатно)

При первом запуске API **автоматически** скачивает GeoNames и импортирует ~200k населённых пунктов РФ, если таблица `places` пуста. Отключить: `GEONAMES_AUTO_IMPORT=false` в `.env`.

Ручной переимпорт (очистка и загрузка заново):

```bash
uv run python scripts/import_geonames_ru.py
```

Подробнее: `data/geonames/README.md`

### 4. Запуск API + бота (polling)

```bash
uv run uvicorn astra.main:app --reload --app-dir src
```

Бот и планировщик уведомлений (09:00 по TZ города) стартуют вместе с приложением.

## Структура

```
src/astra/
├── main.py              # FastAPI + lifespan (бот, scheduler)
├── core/                # config, sentry, prediction_errors
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

Перед сборкой приложения автоматически прогоняются тесты в контейнере.

```bash
cp .env.example .env   # TELEGRAM_BOT_TOKEN обязателен
make up                # тесты → сборка → все сервисы
```

Альтернатива без Make:

```bash
./scripts/docker-up.sh
```

Проверка после запуска:

```bash
make check
# или
curl http://localhost:8000/health
docker compose ps
docker compose logs -f api
```

Только тесты в Docker:

```bash
make test
```

Остановка:

```bash
make down
```

Сервисы: **api** (8000), **worker**, **postgres**, **redis**, **rabbitmq** (15672 — UI), **ollama** (11434).
В `.env` можно оставить `localhost` — в Compose для контейнеров подставляются внутренние URL (`postgres`, `redis`, …).
