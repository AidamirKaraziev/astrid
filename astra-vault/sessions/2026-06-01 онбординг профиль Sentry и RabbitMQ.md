---
tags: [session]
date: 2026-06-01
---

# Сессия 2026-06-01: онбординг, профиль, Sentry, RabbitMQ

## Сделано

### Онбординг и регистрация

- Разделены **этап 1** (сбор данных → `users` + `profiles`) и **этап 2** (приветствие + меню + фоновое предсказание).
- Профиль сохраняется после выбора **места рождения**; город для уведомлений убран из онбординга.
- `greeting_service`, `prediction_delivery_service`; commit до побочных эффектов.
- Исправлен rollback профиля при падении генерации предсказания после «Регистрация завершена».

### Профиль

- Редактирование: имя, дата/время/место рождения, **город для уведомлений** (GeoNames).
- При изменении даты/времени/места рождения — удаление предсказаний за **сегодня** (timezone профиля).
- Карточка профиля **вариант A2**: шапка, короткие места, серия/баллы внизу; кнопка «⭐ Баллы» убрана из главного меню.
- Фикс inline-кнопок: `callback.from_user`, не `message.from_user`.

### RabbitMQ / worker

- `httpx[socks]` для SOCKS proxy в `telegram_send`.
- Гонка generate/send: `commit` до `publish_prediction_send`.
- Дедуп повторных «Предсказание на сегодня»: Redis `astra:prediction:pending:{user}:{date}`.

### Sentry

- `sentry-sdk[fastapi]`, `SENTRY_ENVIRONMENT` (local/dev/prod), `SENTRY_SERVICE` (api/worker).
- `.env.example` обновлён; DSN не в коде.

## Файлы (ключевые)

- `src/astra/services/onboarding_service.py`, `greeting_service.py`, `prediction_pending.py`
- `src/astra/telegram/profile_text.py`, `handlers/places.py`, `handlers/menu.py`
- `src/astra/core/sentry.py`, `workers/handlers.py`

## Проверить на сервере

- `docker compose build && up` после изменений.
- Redis доступен (дедуп предсказаний).
- Профиль → город уведомлений; повторное «Предсказание на сегодня» — одно сообщение в TG.

## Связи

- [[онбординг без города уведомлений город настраивается в профиле]]
- [[дедупликация ежедневного предсказания через Redis pending ключ]]
- [[Sentry environment local dev prod и service api worker]]
