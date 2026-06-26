---
tags: [pattern, llm, compatibility, synastry, prompt]
date: 2026-06-26
status: утверждено
---

# Промпт совместимости синастрия — JSON для LLM

Связано: [[пайплайн совместимости промпт LLM PDF worker]] · [[промпт Astrid v3 — вопрос дня gemma4 e2b]] (другой продукт)

## Назначение

Заполняемый **user message** для LLM: наталы двух людей + список аспектов синастрии → структурированный JSON для PDF (`SynastryReportData`).

Код (план PR1): `src/astra/llm/prompts/compatibility.py`

## System prompt (фиксированный)

```
Ты — Astra, астролог для русскоязычной аудитории. Пишешь разбор синастрии пары:
тепло, без запугивания, с практичными выводами. Отвечаешь только JSON по схеме из запроса.
```

## User template — плейсхолдеры

| Плейсхолдер | Источник |
|-------------|----------|
| `{reader_name}`, `{reader_gender}` | person_a (читатель бота) |
| `{partner_name}`, `{partner_gender}` | person_b |
| `{person_a_json}`, `{person_b_json}` | `json.dumps`, indent=2 |
| `{synastry_aspects_json}` | расчёт Kerykeion, sort by orb_deg |
| `{accuracy_note}` | из `accuracy_tier` обоих |

Тело начинается с: «Составь разбор совместимости для этой пары…»

## JSON-схема ответа LLM

- `tldr` — 2–3 предложения
- `natal_insight` — сочетание карт
- `metrics` — 4 шкалы 0–1 (Притяжение, Эмоциональный контакт, Общение, Долгосрочность)
- `strong_aspects` — orb &lt; 2°, до 4–5 шт., поля: aspect_type, from_planet, to_planet, orb, strength, headline, body
- `working_aspects` — orb 2–6°
- `zone_blocks` — 3 блока: «Что работает само», «Зоны роста», «Опора пары»
- `conclusion_quote`, `conclusion_tip`

Правила для модели: только аспекты из входного списка; «ты» к читателю; без эзотерического клише.

## Постобработка (PR3)

- `json.loads`, strip markdown fences
- Pydantic `CompatibilityLlmOutput`
- mapper → `SynastryReportData` (цвета метрик — из `theme.py`, не от LLM)

## Эталон

Пара Айдамир × Анжела, 12 аспектов (orb 0.13–5.69) — snapshot в тесте PR1.

## Отличие от Astrid v3

| | Daily Astrid | Совместимость |
|---|--------------|---------------|
| Вход | 1 натал + транзиты дня | 2 натала + синастрия |
| Выход | HTML-текст в TG | JSON → PDF |
| Модель (план) | Ollama gemma4:e2b | **Облако** (OpenRouter/Gemini/Grok) — утверждено 2026-06-26 |

~~⚠️ Выбор модели — см. противоречие в [[2026-06-26 PDF синастрия рефакторинг и план совместимости]].~~
