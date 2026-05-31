---
tags: [home, index]
date: 2026-05-31
---

# Astra — карта знаний

Граф знаний проекта **Astra**. AI и люди начинают отсюда.

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

### Паттерны (`knowledge/patterns/`)

- [[имена заметок это утверждения а не категории]]
- [[единое сообщение когда геопозицию не удалось получить или обработать]]

### Интеграции (`knowledge/integrations/`)

- [[MCP servers рекомендации на потом]]

### Отладка (`knowledge/debugging/`)

- [[конфликт хендлеров текста кнопки геолокации с поиском города]]
- [[mihomo показывает COMPATIBLE когда config type http вместо file]]

### Бизнес (`knowledge/business/`)

- [[продукт Astra telegram предсказания RU аудитория]]

## Сессии

- [[2026-05-16 инициализация astra-vault и структуры проекта]]
- [[2026-05-16 discovery и MVP scaffold async telegram бота]]
- [[2026-05-18 геолокация в онбординге и единое сообщение об ошибке]]
- [[2026-05-18 имя в онбординге берётся из Telegram без отдельного шага]]
- [[2026-05-31 Docker mihomo и Telegram на домашнем сервере]]

## Inbox

Необработанные мысли → папка `inbox/`, раз в неделю разбирать в `knowledge/`.

## Спецификация в репо

- Требования: `spec/project.md`
- **Бэклог:** `spec/backlog.md`

## Как открыть в Obsidian

1. Obsidian → **Open folder as vault**
2. Папка: `.../Astra/astra-vault`
3. Graph View: `Ctrl+G` / `Cmd+G`
