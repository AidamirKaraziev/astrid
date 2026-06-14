---
tags: [session, llm, astrid, прогноз]
date: 2026-06-14
---

# Astrid v3 — вопрос дня + прогноз + совет

## Контекст

Переход с v2 (эмодзи-секции, число/цвет) на v3: **вопрос дня в push**, затем прогноз и совет. 6 архетипов вопроса, один запрос Ollama, детерминированный выбор per user+day.

## Фазы

1. **Промпт + архетипы** — `QuestionArchetype`, system/user v3
2. **Sanitize + validate** — 3 блока, temp 0.76, body 3–6 предл.
3. **Pipeline** — `astro_service` → `question_archetype_id` в JSONB
4. **Smoke + vault** — `scripts/smoke_astrid_v3.py`, паттерн v3
5. **E2E local** — `scripts/e2e_astrid_v3.py`, чеклист, 3/3 OK, p50 16.6s

## Smoke local (gemma4:e2b)

- Aidamir / `avoided_truth` — push 44 симв. ✓
- Марина / `urgent_vs_important` — push 36 симв. ✓

## E2E local (2026-06-14)

- 3 даты, 3 архетипа, все чеклисты ✓
- p50 latency: **16.6s** (M4 Pro)
- Отчёт: `docs/e2e/astrid-v3-e2e.md`
- 66 pytest (retry на validation fail)

## Следующее

- E2E **deadtiger + TG** — ручной чеклист в `docs/e2e/astrid-v3-e2e.md`
- PERF-2: latency/RAM на deadtiger

Связано: [[промпт Astrid v3 — вопрос дня gemma4 e2b]] · [[продукт Astra telegram предсказания RU аудитория]]
