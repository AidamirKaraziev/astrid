---
tags: [atlas, stack]
date: 2026-05-16
---

# Стек: Python 3.12, uv и FastAPI

## Runtime

- **Python:** 3.12 (`.python-version`)
- **Менеджер пакетов:** [uv](https://docs.astral.sh/uv/) — см. [[uv выбран как менеджер зависимостей вместо pip]]

## Framework

- **FastAPI** ≥ 0.136 — async HTTP API, OpenAPI из коробки
- **Pydantic** — валидация request/response (транзитивная зависимость FastAPI)
- **Starlette** — ASGI-слой под FastAPI

## Запуск (после настройки приложения)

```bash
uv sync
uv run fastapi dev main.py   # или uvicorn после рефакторинга
```

## Связи

- [[архитектура проекта Astra на старте scaffold]]
- [[деплой пока не настроен]]
