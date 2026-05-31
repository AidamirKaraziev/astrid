---
tags: [session, deploy, docker, telegram, mihomo]
date: 2026-05-31
---

# Docker, mihomo и Telegram на домашнем сервере

## Цель сессии

Упаковать проект в Docker, запустить на домашнем сервере без белого IP, обеспечить доступ бота к Telegram Bot API (блок исходящих у провайдера).

## Сделано

### Docker / Compose

- Multi-stage `Dockerfile` (`dev` для pytest, `runtime` для api/worker).
- `docker-compose.yml`: postgres, redis, rabbitmq, ollama, api, worker, profile `test`.
- `Makefile`, `scripts/docker-up.sh` — тесты → сборка → запуск (`make up`).
- `.dockerignore`.

### Код Astra

- `TELEGRAM_PROXY_URL` в config + aiogram `AiohttpSession(proxy=...)`.
- Polling supervisor: `delete_webhook`, авторестарт, отдельный Bot для рассылки.
- `UpdateLoggingMiddleware`, `scripts/check-telegram-bot.sh`.
- Зависимость `aiohttp-socks`.

### Домашний сервер (deadtiger)

- **Проблема:** polling стартовал и падал; Telegram не отвечал — нет исходящего доступа к `api.telegram.org`.
- **VPN:** mihomo на Ubuntu 24 без GUI; подписка VLESS (Happ Plus).
- **Ключевые находки:**
  - `tg://proxy` и MTProto — **не** для Bot API.
  - Mihomo `type: http` + VLESS URL → один узел `COMPATIBLE` — **не работает**.
  - Рабочая схема: `scripts/vless-sub-to-clash.py` → `/etc/mihomo/proxies.yaml` + `config.yaml` **`type: file`**.
  - Подписка: `u.mrzb.artydev.ru` → 307 → `rsub.network-a1.cc/...`; скачивать с `curl -L`.
  - AUTO / Happy (`web.max.ru`, SNI `icloud.com`) — битые узлы; фильтровать.
  - Astra в Docker: `TELEGRAM_PROXY_URL=socks5://172.17.0.1:7890` (IP Docker gateway, не `127.0.0.1`).

### Документация в репо

- `scripts/mihomo-telegram-setup.md` — настройка + диагностика A→I.
- `scripts/vless-sub-to-clash.py` — конвертер подписки.

## Результат

На сервере: mihomo + 27 узлов в PROXY, `getMe` через SOCKS5 OK, бот готов к работе через `TELEGRAM_PROXY_URL`.

## Связи

- [[mihomo читает VLESS подписку через proxies.yaml type file]]
- [[TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo]]
- [[mihomo показывает COMPATIBLE когда config type http вместо file]]
- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]

## Следующая сессия

- Проверить бота end-to-end в Docker после стабильного uptime mihomo.
- Перевыпустить ссылку подписки VPN (светилась в чате).
- Бэклог: INF-1, UX-1, AI-2 — см. [[текущие приоритеты]].
