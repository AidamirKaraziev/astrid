---
tags: [decision, knowledge, obsidian]
date: 2026-05-16
---

# Knowledge vault astra-vault внутри репозитория

## Контекст

Нужна долгосрочная память для AI (Cursor / Claude Code): решения, баги, история сессий.

## Решение

Папка **`astra-vault/`** в корне репозитория — Obsidian Knowledge Vault по методологии из гайда Obsidian + Claude Code.

Имя **astra-vault** (не `astra_vaulte`): kebab-case, сразу ясно, что это vault проекта Astra.

## Почему внутри репо

- Версионирование вместе с кодом
- Один клон — и код, и знания
- Cursor/Claude читают файлы по относительному пути

## Интеграция с AI

- `CLAUDE.md` — инструкции при старте и «сохрани сессию»
- `.cursor/rules/astra-knowledge-vault.mdc` — то же для Cursor

## Структура

`00-home/`, `atlas/`, `knowledge/*`, `sessions/`, `inbox/`

## Связи

- [[имена заметок это утверждения а не категории]]
- [[2026-05-16 инициализация astra-vault и структуры проекта]]
- Карта: [[index]]
