---
tags: [home, index]
date: 2026-05-31
---

# Astra — карта знаний

Граф знаний проекта **Astra**. AI и люди начинают отсюда.

## Автор

→ [[обо мне]]

## Сейчас в работе

→ [[текущие приоритеты]]

## Atlas (архитектура, редко меняется)

| Тема | Заметка |
|------|---------|
| Архитектура MVP | [[архитектура MVP monolith async 2026-05-16]] |
| Scaffold (устар.) | [[архитектура проекта Astra на старте scaffold]] |
| Стек | [[стек Python 3.12 uv и FastAPI]] |
| Деплой | [[деплой пока не настроен]] · [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]] |

## Knowledge

### Решения (`knowledge/decisions/`)

- [[uv выбран как менеджер зависимостей вместо pip]]
- [[knowledge vault astra-vault внутри репозитория]]
- [[идентификация через telegram_id без fastapi-users в MVP]]
- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
- [[scheduler рассылки в том же процессе что API]]
- [[на Desktop request_location приходит как текст а не location]]
- [[Telegram Bot API не передаёт тип клиента в Message]]
- [[имя в онбординге по умолчанию из Telegram правка в Профиле]]
- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]
- [[TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo]]
- [[mihomo читает VLESS подписку через proxies.yaml type file]]
- [[онбординг без города уведомлений город настраивается в профиле]]
- [[дедупликация ежедневного предсказания через Redis pending ключ]]
- [[Sentry environment local dev prod и service api worker]]

### Паттерны (`knowledge/patterns/`)

- [[промпт Astrid v2 — 4 предложения gemma4 e2b]]
- [[промпт Astrid — ежедневный прогноз 600–1000 символов]]
- [[имена заметок это утверждения а не категории]]
- [[единое сообщение когда геопозицию не удалось получить или обработать]]
- [[карточка профиля A2 сокращение названий GeoNames]]

### Интеграции (`knowledge/integrations/`)

- [[MCP servers рекомендации на потом]]

### Отладка (`knowledge/debugging/`)

- [[конфликт хендлеров текста кнопки геолокации с поиском города]]
- [[mihomo показывает COMPATIBLE когда config type http вместо file]]
- [[RabbitMQ send раньше commit generate и отсутствие socksio]]

### Бизнес (`knowledge/business/`)

- [[продукт Astra telegram предсказания RU аудитория]]
- [[портфель монетизации Astra]] · [[оценка идей монетизации Astra 2026-06-13]]

## Сессии

- [[2026-05-16 инициализация astra-vault и структуры проекта]]
- [[2026-05-16 discovery и MVP scaffold async telegram бота]]
- [[2026-05-18 геолокация в онбординге и единое сообщение об ошибке]]
- [[2026-05-18 имя в онбординге берётся из Telegram без отдельного шага]]
- [[2026-05-31 Docker mihomo и Telegram на домашнем сервере]]
- [[2026-06-01 онбординг профиль Sentry и RabbitMQ]]
- [[2026-06-02 промпт Astrid короткий прогноз и постобработка]]
- [[2026-06-12 промпт Astrid v2 gemma4 e2b]]
- [[2026-06-12 имя в начале прогноза Astrid]]

## Inbox

Необработанные мысли → папка `inbox/`, раз в неделю разбирать в `knowledge/`.

## Спецификация в репо

- Требования: `spec/project.md`
- **Бэклог:** `spec/backlog.md`

## Как открыть в Obsidian

1. Obsidian → **Open folder as vault**
2. Папка: `.../Astra/astra-vault`
3. Graph View: `Ctrl+G` / `Cmd+G`
