---
tags: [pattern, llm, astrid, прогноз, gemma4]
date: 2026-06-12
---

# Промпт Astrid v2 — 4 предложения gemma4:e2b

Связано: [[продукт Astra telegram предсказания RU аудитория]], [[стек Python 3.12 uv и FastAPI]]

## Роль

**Astrid** — астролог в TG-боте Astra. Персональный дневной прогноз: натал + топ-транзиты, не солнечный гороскоп.

## Код

- Промпт и постобработка: `src/astra/llm/prompts/astrid.py`
- Ollama: `src/astra/llm/ollama.py` (`temperature` 0.72, `num_predict` 380, `num_ctx` 4096, `think=false`)
- Транзиты: `src/astra/astro/transits.py`
- Fallback без LLM: нет — при ошибке LLM `LlmGenerationError`, retry в worker (`prediction_generation.py`)

## Входные данные

| Поле | Источник |
|------|----------|
| имя (без склонений) | `Profile.display_name` |
| дата/время/место рождения | `Profile` |
| Солнце, Луна, ASC | `NatalChartData` |
| транзиты | компактный JSON: transit, aspect, natal, orb, theme |

## Требования к тексту

- **4 предложения** в основном блоке (`MIN_SENTENCES = MAX_SENTENCES = 4`)
- обращение на **«ты»**; первое предложение начинается с **имени в именительном**: «Марина, сегодня…»
- имя не склоняется; дальше в тексте не повторяется
- без склонений в промпте (`inflect_name` убран из astrid)
- запрет клише: внутренние процессы, прекрасное время, гармония, ритм…
- sanitize подменяет число дня `12` (bias e2b) на детерминированное

## Формат Telegram

```
✨ Прогноз дня
[текст]
💡 Совет дня: ...
🔢 Число дня: ...
🎨 Цвет дня: ...
```

## История

- До 2026-06-12: v1 с склонениями, 3–5 предложений, длинный system
- 2026-06-12: **v2** под gemma4:e2b, без склонений, 4 предложения
- 2026-06-14: **superseded** → [[промпт Astrid v3 — вопрос дня gemma4 e2b]]
