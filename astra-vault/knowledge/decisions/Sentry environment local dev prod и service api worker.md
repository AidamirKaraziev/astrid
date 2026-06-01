---
tags: [decision, sentry, observability]
date: 2026-06-01
---

# Sentry: environment local/dev/prod и service api/worker

## Решение

- Один DSN, фильтр в UI по **Environment**: `SENTRY_ENVIRONMENT` = `local` | `dev` | `prod`.
- Тег `service`: `api` | `worker` (`SENTRY_SERVICE`, в Compose переопределяется для worker).
- `server_name`: `astra-api` / `astra-worker`.
- DSN только из env; `send_default_pii` настраивается флагом.

## Зависимости

- `sentry-sdk[fastapi]`, `httpx[socks]` (worker шлёт в TG через proxy).

## Связи

- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]
