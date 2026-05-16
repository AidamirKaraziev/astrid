---
tags: [home, index]
date: 2026-05-16
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
| Деплой | [[деплой пока не настроен]] |

## Knowledge

### Решения (`knowledge/decisions/`)

- [[uv выбран как менеджер зависимостей вместо pip]]
- [[knowledge vault astra-vault внутри репозитория]]
- [[идентификация через telegram_id без fastapi-users в MVP]]
- [[monolith FastAPI aiogram без RabbitMQ в MVP]]
- [[scheduler рассылки в том же процессе что API]]

### Паттерны (`knowledge/patterns/`)

- [[имена заметок это утверждения а не категории]]

### Интеграции (`knowledge/integrations/`)

- [[MCP servers рекомендации на потом]]

### Отладка (`knowledge/debugging/`)

_Пока пусто._

### Бизнес (`knowledge/business/`)

- [[продукт Astra telegram предсказания RU аудитория]]

## Сессии

- [[2026-05-16 инициализация astra-vault и структуры проекта]]
- [[2026-05-16 discovery и MVP scaffold async telegram бота]]

## Inbox

Необработанные мысли → папка `inbox/`, раз в неделю разбирать в `knowledge/`.

## Спецификация в репо

Исходные требования: `spec/project.md` (синхронизировать с vault при изменениях).

## Как открыть в Obsidian

1. Obsidian → **Open folder as vault**
2. Папка: `.../Astra/astra-vault`
3. Graph View: `Ctrl+G` / `Cmd+G`
