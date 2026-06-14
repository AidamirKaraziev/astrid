# Astra — спецификация продукта

> Статус: актуально на 2026-06-14. Задачи и спринты — в [backlog.md](backlog.md).

## Цель

Telegram-бот с **ежедневными персональными астрологическими предсказаниями** для RU-аудитории. Бесплатный MVP с геймификацией (баллы, streak, рефералы) и заделом под платные разборы.

## Аудитория

- В основном женщины, интерес к астрологии и «магическому» контексту.
- Канал MVP: **Telegram** (polling / webhook на prod).

## MVP scope (что уже есть или в работе)

| Область | Состояние |
|---------|-----------|
| Онбординг (имя, дата/время/место рождения) | ✓ |
| Справочник мест РФ (GeoNames, ~200k) | ✓ |
| Натальная карта + транзиты (kerykeion) | ✓ |
| Ежедневное предсказание через LLM (Ollama, gemma4:e2b) | ✓ код, local E2E ✓, deadtiger/TG — в работе |
| Формат Astrid v3: вопрос дня (push) + прогноз + совет | ✓ |
| Планировщик уведомлений 09:00 по TZ города | ✓ |
| Баллы, streak, реферальная ссылка | ✓ базово |
| REST API `/v1/*` (без JWT в MVP) | ✓ |
| Docker Compose: api, worker, postgres, redis, rabbitmq, ollama | ✓ |

## Вне scope MVP

- Mini App, Web/mobile
- JWT / полноценная auth для API
- Платные продукты (синастрия, таро и т.д.) — после retention-метрик
- Multi-LLM / Langfuse

## Архитектура (кратко)

- **Monolith FastAPI** + aiogram в одном процессе API (бот, scheduler).
- **Worker** — генерация предсказаний через RabbitMQ.
- **PostgreSQL** — пользователи, профили, места, предсказания.
- **Redis** — FSM бота, дедупликация pending-генерации.
- **Ollama** — локальная LLM (CPU-only на deadtiger).

Подробнее: `astra-vault/atlas/архитектура MVP monolith async 2026-05-16.md`

## Нефункциональные требования

- Python ≥ 3.12, зависимости через **uv**
- Деплой: Docker Compose на домашнем сервере (deadtiger)
- LLM: модель ≤ ~4B Q4, генерация в фоне (worker)

## Связи

- Бэклог: [backlog.md](backlog.md)
- Vault: `astra-vault/knowledge/business/продукт Astra telegram предсказания RU аудитория.md`
