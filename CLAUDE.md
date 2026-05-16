# Astra

Python-бэкенд на FastAPI. Менеджер зависимостей: [uv](https://docs.astral.sh/uv/). Python ≥ 3.12.

## Стек

- **Runtime:** Python 3.12
- **Framework:** FastAPI
- **Упаковка:** pyproject.toml + uv.lock

## Структура репозитория

```
Astra/
├── main.py           # точка входа (пока шаблон PyCharm)
├── pyproject.toml
├── spec/             # спецификация и требования
└── astra-vault/      # Obsidian Knowledge Vault
```

## Конвенции кода

- Типизация и валидация через Pydantic (встроено в FastAPI).
- Секреты только в `.env`, не коммитить.
- Язык заметок в vault: русский. Имена файлов — **утверждения**, не категории.

## Obsidian Knowledge Vault

Хранилище знаний: `astra-vault/` (абсолютный путь: `/Users/ajdamirkaraziev/PycharmProjects/Astra/astra-vault/`)

Откройте эту папку в Obsidian как отдельное vault (Create new vault → Open folder as vault).

### При старте сессии

1. Прочитай `astra-vault/00-home/index.md` и `astra-vault/00-home/текущие приоритеты.md`.
2. Если задача касается модуля, интеграции или прошлого решения — прочитай релевантную заметку из `knowledge/` или `atlas/`.
3. Используй wiki-ссылки `[[имя заметки]]` для навигации между связанными темами.

### При завершении (пользователь: «сохрани сессию»)

1. Создай заметку в `sessions/` с датой в названии.
2. Обнови `00-home/текущие приоритеты.md`.
3. Новое архитектурное решение → `knowledge/decisions/`.
4. Разобранный баг → `knowledge/debugging/`.
5. Повторяемый приём в коде → `knowledge/patterns/`.
6. Обнови `00-home/index.md`, если появились новые заметки.

### Именование заметок

Название файла = утверждение (например: `rate limit API 500 запросов потом 429.md`), не категория (`bugs.md`).
