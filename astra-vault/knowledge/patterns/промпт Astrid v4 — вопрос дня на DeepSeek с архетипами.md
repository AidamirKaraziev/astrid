---
tags: [pattern, llm, astrid, прогноз, deepseek]
date: 2026-07-21
---

# Промпт Astrid v4 — вопрос дня на DeepSeek с архетипами

Действующий формат ежедневного прогноза. Пришёл на смену v3 (gemma4:e2b, Ollama) — локальная LLM удалена 2026-07-08, см. [[локальная LLM Ollama удалена весь daily на DeepSeek]].

## Код

| Модуль | Назначение |
|--------|------------|
| `src/astra/llm/prompts/astrid_v4.py` | `SYSTEM_PROMPT_V4`, `build_context_payload`, `build_user_message_v4`, `resolve_archetype` |
| `src/astra/llm/prompts/astrid.py` | архетипы (`QUESTION_ARCHETYPES`, `pick_question_archetype`, `format_archetype_hint`), sanitize/validate, анти-клише |
| `src/astra/services/astro_service.py` | `question_archetype_id` сохраняется в JSONB `astro_context` |

## Формат Telegram

```
[вопрос дня?]

Имя, сегодня… (прогноз, имя в именительном в 1-м предложении)

[1 предложение совета]
```

Push preview = вопрос дня (первая строка). Без эмодзи-заголовков, без числа/цвета дня.

## Архетипы вопроса (6 семейств)

Детерминированный выбор: `sha256(user_id + date) % 6` — retry в тот же день даёт тот же архетип.

| id | тема |
|----|------|
| `postpone` | откладывание, приоритеты |
| `right_or_close` | правота vs близость |
| `urgent_vs_important` | важное vs срочное |
| `listen_not_convince` | слушать vs переубеждать |
| `let_go_new` | отпустить ради нового |
| `avoided_truth` | правда в общении |

В промпт идёт theme + example (модель перефразирует), не жёсткий шаблон.

## Sanitize / validate

Провал sanitize/validate → `LlmGenerationError` → retry в worker (до 15 попыток). Анти-клише и запрещённые фразы — `_format_forbidden_phrases` / `_format_cliche_words` из `astrid.py`.

## Связи

- [[локальная LLM Ollama удалена весь daily на DeepSeek]]
- [[продукт Astra telegram предсказания RU аудитория]]
