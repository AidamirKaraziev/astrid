---
tags: [decision, llm, compatibility, pydantic]
date: 2026-07-02
status: черновик — ждёт утверждения
---

# Split Contract: LLM и Pydantic для совместимости

Связано: [[промпт совместимости синастрия JSON для LLM]] · [[2026-07-02 staged progress pipelines и диагностика LLM совместимости]]

## Проблема

Промпт, ручное `_json_schema_description()` и Pydantic `CompatibilityLlmOutput` — **три источника правил**. Модель нарушает орбы/длины → весь отчёт `failed` без сообщения пользователю.

## Рекомендуемое решение (вариант B)

```
CompatibilityPromptInput + synastry_aspects
        ↓
LLM → CompatibilityLlmRaw (только тексты и смысл)
        ↓
assemble_llm_output(raw, input) → CompatibilityLlmOutput
        ↓
PDF mapper (без изменений по сути)
```

### LLM генерирует
- `tldr`, `natal_insight`, `conclusion_*`
- `aspect_interpretations[]` — `headline` + `body` по индексу аспекта (порядок = sorted by orb)
- `metrics` — 4 float 0–1 (подписи подставляет код)
- `zone_items` — 3 списка пунктов (заголовки блоков — код)

### Код собирает
- `strong_aspects` / `working_aspects` по `orb_deg` из входа
- `orb`, `aspect_type`, `from_planet`, `to_planet`, `strength`
- порядок metrics, заголовки zone_blocks
- `clamp_text()` до лимитов PDF

### Промпт
- Описание схемы **автоген из Pydantic** (`CompatibilityLlmRaw`), не руками.
- Убрать из промпта всё, что делает код.

### Страховка
- Retry ×2 при `json_invalid`
- Уведомление в Telegram при невосстановимом фейле (как daily prediction)

## Альтернативы (отклонены как основной путь)

| Вариант | Плюс | Минус |
|---------|------|-------|
| A — normalize текущего JSON | быстро | модель всё ещё генерит лишнее |
| C — A сейчас, B потом | быстрый hotfix | двойная работа |

## Критерий готовности

- Два кейса из prod-логов (орб 1.46, natal_insight >260) не роняют пайплайн.
- Тесты: assemble, clamp, parse raw, smoke на фикстуре Айдамир × Анжела.
