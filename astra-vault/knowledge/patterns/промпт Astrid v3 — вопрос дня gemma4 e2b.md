---
tags: [pattern, llm, astrid, прогноз, gemma4]
date: 2026-06-14
---

# Промпт Astrid v3 — вопрос дня gemma4:e2b

Связано: [[продукт Astra telegram предсказания RU аудитория]], [[промпт Astrid v2 — 4 предложения gemma4 e2b]] (superseded)

## Роль

**Astrid** — астролог в TG-боте Astra. Персональный дневной прогноз: натал + топ-транзиты. **Push preview** = вопрос дня (первая строка).

## Код

| Модуль | Назначение |
|--------|------------|
| `src/astra/llm/prompts/astrid.py` | промпт, 6 архетипов вопроса, sanitize v3, validate |
| `src/astra/llm/ollama.py` | Ollama: `temp=0.76`, `num_predict=340`, validate → retry |
| `src/astra/services/astro_service.py` | `pick_question_archetype`, `question_archetype_id` в JSONB |
| `scripts/smoke_astrid_v3.py` | быстрый smoke (2 кейса) |
| `scripts/e2e_astrid_v3.py` | полный E2E (3 даты + чеклист + latency) |

## Формат Telegram

```
[вопрос дня?]

Имя, сегодня… (3–6 предложений, ~4 в промпте)

[1 предложение совета]
```

Без эмодзи-заголовков, без числа/цвета дня.

## Архетипы вопроса (6 семейств)

Детерминированный выбор: `sha256(user_id + date) % 6`. Retry в тот же день → тот же архетип.

| id | тема |
|----|------|
| `postpone` | откладывание, приоритеты |
| `right_or_close` | правота vs близость |
| `urgent_vs_important` | важное vs срочное |
| `listen_not_convince` | слушать vs переубеждать |
| `let_go_new` | отпустить ради нового |
| `avoided_truth` | правда в общении |

Модель **перефразирует** — в промпт идёт theme + example, не жёсткий шаблон.

## Требования к тексту

- **Вопрос:** 15–65 симв., таинственный, намекает на суть дня, без планет
- **Прогноз:** ~4 предложения (sanitize/validate допускают **3–6**, 2–7 на validate fail); имя в **именительном** в 1-м предложении
- **Совет:** 1 предложение
- Anti-cliche, anti-CJK — как в v2
- `astro_context.question_archetype_id` сохраняется в БД

## Validate → retry

Провал sanitize/validate → `LlmGenerationError` → worker retry (до 15 попыток).

## Smoke 2026-06-14 (local gemma4:e2b)

```
Aidamir · avoided_truth · push 44 симв.
Марина · urgent_vs_important · push 36 симв.
2/2 OK
```

## E2E 2026-06-14 (local, 3 даты)

```
3/3 OK · p50 16.6s · scripts/e2e_astrid_v3.py
Отчёт: docs/e2e/astrid-v3-e2e.md
```

## История

- 2026-06-12: v2 — 4 предложения + совет/число/цвет
- 2026-06-14: **v3** — вопрос дня + прогноз + совет, архетипы, validate
