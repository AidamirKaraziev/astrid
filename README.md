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

### 3.1. Справочник городов и деревень СНГ (GeoNames, бесплатно)

При первом запуске API **автоматически** скачивает GeoNames и импортирует ~337k населённых пунктов пятнадцати постсоветских стран, если таблица `places` пуста. Отключить: `GEONAMES_AUTO_IMPORT=false` в `.env`.

Ручной переимпорт (обновляет записи по `geoname_id`, места рождения людей не теряются):

```bash
uv run python scripts/import_geonames.py
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

### Регистрация: тесты на живой базе

Основная масса тестов подменяет сессию БД моком — так быстрее, но именно
поэтому поломка старта в слое БД однажды прошла мимо всех. Воронку
регистрации проверяем иначе, без моков:

| Файл | Что охраняет |
|------|--------------|
| `tests/test_registration_funnel_e2e.py` | `/start` → онбординг → профиль в базе через боевой `Dispatcher` и живой Postgres |
| `tests/test_db_session_wiring.py` | сессия БД открывается: ручки FastAPI и админка не падают в 500 |
| `tests/test_places_search.py` | поиск города: 150 известных городов СНГ обязаны находиться первой строкой |
| `tests/fake_telegram.py` | ненастоящий Telegram: транспорт, который пишет ответы бота в список |

Этим тестам нужны **Postgres и Redis** (`make infra` + `alembic upgrade head`).
Без них локально они пропускаются с подсказкой, а в CI и в `make test` —
падают: молча пропущенный тест регистрации ничем не лучше отсутствующего.

Приёмка справочника городов требует ещё и самого справочника, которого в CI
нет (качать 200 МБ на каждый прогон незачем). Поэтому она встроена в импорт:
`scripts/import_geonames.py` прогоняет контрольный список и **падает**, если
хоть один известный город не находится первой строкой. Список городов —
`src/astra/places/control_list.py`, пополнять при каждом баге.

Быстрая проверка перед выкаткой:

```bash
uv run pytest tests/test_registration_funnel_e2e.py tests/test_db_session_wiring.py -v
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

### Если реестры образов заблокированы

Симптом: `make up` висит на `[internal] load metadata for docker.io/...` или
слои качаются по 0 B. Docker Hub отдаёт российским адресам отказ, ghcr.io
режется на стороне провайдера.

`ghcr.io` из сборки убран — uv ставится с PyPI. Остаётся docker.io, лечится
одним из двух способов.

**1. Зеркало на уровне демона (лечит всё сразу, включая postgres/redis/rabbitmq).**
`/etc/docker/daemon.json` на сервере:

```json
{
  "registry-mirrors": [
    "https://mirror.gcr.io",
    "https://dockerhub.timeweb.cloud"
  ]
}
```

```bash
sudo systemctl restart docker && docker info | grep -A3 'Registry Mirrors'
```

Оба зеркала проверены 06.08.2026 — отдают манифесты python/postgres/rabbitmq.
Список живой: проверить кандидата до правки демона можно так (ожидается `200`),

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Accept: application/vnd.oci.image.index.v1+json' https://mirror.gcr.io/v2/library/python/manifests/3.12-slim-bookworm
```

а после правки — `docker pull alpine`.

**2. Переменные в `.env` (если менять демон нельзя).** Каждый образ можно
перенаправить точечно:

```env
PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim-bookworm
POSTGRES_IMAGE=mirror.gcr.io/library/postgres:16-alpine
REDIS_IMAGE=mirror.gcr.io/library/redis:7-alpine
RABBITMQ_IMAGE=mirror.gcr.io/library/rabbitmq:3-management-alpine
```

**3. Свой прокси наружу** — самый надёжный вариант, если он есть. Прокси
прописывается демону, а не в compose:

```bash
sudo systemctl edit docker
# [Service]
# Environment="HTTPS_PROXY=http://<host>:<port>"
sudo systemctl restart docker
```

PyPI и deb.debian.org не блокируются — остальная часть сборки проходит как есть.

Сервисы: **api** (8000), **worker**, **postgres**, **redis**, **rabbitmq** (15672 — UI).
В `.env` можно оставить `localhost` — в Compose для контейнеров подставляются внутренние URL (`postgres`, `redis`, …).

## LLM / Astrid v4

Ежедневное предсказание: **вопрос дня** (push preview) + персональный прогноз + конфликт дня. Генерация — **DeepSeek** (облако): нужны `DEEPSEEK_ENABLED=true` и `DEEPSEEK_API_KEY` в `.env`. Код: `src/astra/llm/prompts/astrid_v4.py` (промпт) и `src/astra/llm/daily_llm.py` (провайдер).

Локальная LLM (Ollama) удалена в июле 2026 — см. `astra-vault/knowledge/decisions/`.
