---
tags: [decision, tooling]
date: 2026-05-16
---

# uv выбран как менеджер зависимостей вместо pip

## Контекст

Проект инициализирован с `pyproject.toml` и `uv.lock`.

## Решение

Использовать **uv** для установки зависимостей и запуска (`uv sync`, `uv run`).

## Почему

- Быстрая установка и воспроизводимый lockfile
- Единый инструмент вместо pip + venv + pip-tools
- Нативная работа с `pyproject.toml`

## Последствия

- В README/доках указывать команды через `uv`, не `pip install`
- `.venv/` в gitignore

## Связи

- [[стек Python 3.12 uv и FastAPI]]
