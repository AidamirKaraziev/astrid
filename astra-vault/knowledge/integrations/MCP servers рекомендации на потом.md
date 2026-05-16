---
tags: [integrations, mcp, ai-dev]
date: 2026-05-16
---

# MCP servers — рекомендации на потом

Заметка из architecture review. **MVP уже можно разрабатывать без них.**

## Сейчас (MVP)

| MCP | Зачем |
|-----|-------|
| Docker | compose, локальный parity |
| GitHub | CI, PR |
| PostgreSQL | отладка схемы (только dev) |
| OpenAPI | контракты API |
| Telegram Bot | тест сообщений |
| Sentry | ошибки после деплоя |

## Позже (по мере роста)

| MCP | Когда |
|-----|-------|
| Langfuse | подключение реального LLM |
| Redis MCP | отладка FSM/кэша под нагрузкой |
| Stripe / Telegram Payments | монетизация |
| Pinecone / vector DB | RAG |
| Temporal | длинные AI-workflows |
| Kubernetes / Terraform | prod infra |
| Grafana | SLO после метрик |
| ClickHouse | product analytics на масштабе |
| n8n | только ops/marketing automation |

## Риски MCP в prod

- Write-доступ к БД из IDE
- Утечка секретов через промпты

## Связи

- [[2026-05-16 discovery и MVP scaffold async telegram бота]]
