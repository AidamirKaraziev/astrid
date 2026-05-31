---
tags: [decision, telegram, deploy, mihomo]
date: 2026-05-31
---

# TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo

## Контекст

Домашний сервер без гарантированного доступа к `api.telegram.org`. Polling и sendMessage требуют **исходящий HTTPS**, не белый IP.

## Решение

1. На хосте: **mihomo** слушает SOCKS5 `127.0.0.1:7890`, правила — только `telegram.org` / `t.me` через VPN.
2. В `.env` Astra:

```env
TELEGRAM_PROXY_URL=socks5://172.17.0.1:7890
```

IP — **шлюз Docker-сети** (`docker network inspect … | grep Gateway`), не `127.0.0.1` (контейнер не видит localhost хоста).

3. В коде: `AiohttpSession(proxy=settings.telegram_proxy_url)` при создании Bot; worker `httpx` с тем же proxy.

## Не подходит

- `tg://proxy?...` (MTProto для клиента Telegram).
- SOCKS5 на MTProto-порт (7443).
- `127.0.0.1:7890` внутри контейнера api.

## Связи

- [[mihomo читает VLESS подписку через proxies.yaml type file]]
- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]
- `scripts/mihomo-telegram-setup.md`
