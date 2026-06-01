---
tags: [debugging, rabbitmq, worker]
date: 2026-06-01
---

# RabbitMQ: send раньше commit generate и отсутствие socksio

## Симптомы

- `RuntimeError: Prediction not ready yet` в worker после успешного лога generate.
- `ImportError: socksio` при `send_telegram_html` с SOCKS proxy.

## Причины

1. `publish_prediction_send` до `commit` транзакции generate — send-воркер не видел строку в Postgres.
2. В Docker-образе был `httpx` без extra `[socks]`.

## Исправления

- `await session.commit()` в `handle_prediction_generate` перед publish send.
- `httpx[socks]` в `pyproject.toml`.
- Retry чтения предсказания в send (5× 0.1 с).

## Связи

- [[дедупликация ежедневного предсказания через Redis pending ключ]]
