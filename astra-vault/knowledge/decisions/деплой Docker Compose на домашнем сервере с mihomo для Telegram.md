---
tags: [decision, deploy, docker]
date: 2026-05-31
---

# Деплой Docker Compose на домашнем сервере с mihomo для Telegram

## Контекст

MVP на домашнем Linux без публичного IP. Нужен один стек: API + worker + postgres + redis + rabbitmq + ollama.

## Решение

- **Docker Compose** в корне репо; prod-like env через `x-app-env` (внутренние URL `postgres`, `redis`, …).
- Запуск: `make up` (тесты в контейнере → сборка → `docker compose up`).
- Telegram с хоста без VPN: **mihomo** на хосте, не в Compose (проще маршрутизация и обновление подписки).
- Healthcheck api: `GET /health`.

## Ограничения

- Не prod-HA; домашний сервер + ручной mihomo.
- Подписка VPN и `.env` не в git.

## Связи

- [[TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo]]
- [[архитектура MVP monolith async 2026-05-16]]
- `README.md`, `scripts/mihomo-telegram-setup.md`
