---
tags: [atlas, architecture]
date: 2026-05-16
---

# Архитектура проекта Astra на старте scaffold

Проект в стадии **нулевого scaffold**: один `main.py` (шаблон IDE), зависимость [[стек Python 3.12 uv и FastAPI]].

## Текущее состояние

```
Astra/
├── main.py              # точка входа (ещё не API)
├── pyproject.toml
├── uv.lock
├── CLAUDE.md            # правила для AI
├── spec/project.md      # черновик требований
└── astra-vault/         # этот vault
```

## Целевая форма (черновик)

По мере роста — типичная раскладка FastAPI:

- `app/main.py` — создание `FastAPI()`, lifespan
- `app/api/routes/` — роутеры
- `app/core/config.py` — настройки из env
- `app/models/` — Pydantic-схемы
- `tests/`

Обновлять эту заметку при первом рефакторинге структуры.

## Связи

- Стек: [[стек Python 3.12 uv и FastAPI]]
- Решения: [[uv выбран как менеджер зависимостей вместо pip]], [[knowledge vault astra-vault внутри репозитория]]
- Спека: `spec/project.md`
