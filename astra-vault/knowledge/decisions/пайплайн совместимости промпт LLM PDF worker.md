---
tags: [decision, compatibility, synastry, pdf, worker]
date: 2026-06-26
status: утверждено
---

# Пайплайн совместимости: промпт → LLM → PDF → worker

Связано: [[2026-06-26 PDF синастрия рефакторинг и план совместимости]] · [[промпт совместимости синастрия JSON для LLM]]

## Решение

Автоматический цикл продукта «Совместимость пары»:

```mermaid
flowchart LR
  A[Кнопка TG] --> B[FSM партнёр]
  B --> C[Заказ в БД]
  C --> D[Worker]
  D --> E[Kerykeion synastry]
  E --> F[Промпт + LLM JSON]
  F --> G[Mapper]
  G --> H[generate_synastry_pdf]
  H --> I[sendDocument]
```

## Что уже есть

- PDF-движок: `src/astra/reports/synastry/` + `docs/synastry-pdf.md`
- Worker-паттерн: daily prediction (RabbitMQ generate → send)
- Kerykeion: только natal×transit в daily; **natal×natal — сделать**

## Что строим (4 PR)

1. Промпт-шаблон + preview CLI
2. `astro/synastry.py`
3. `compatibility_generate.py`
4. mapper + worker + FSM

## MVP scope (утверждено 2026-06-26, выбор Аида)

| Решение | Выбор |
|---------|--------|
| Продукт | **Полная синастрия пары** — 2 натала, PDF |
| Оплата | **MVP бесплатно** для A/B качества; Stars после PR4 |
| LLM | **Только облако** (OpenRouter/Gemini/Grok) |
| Кнопка «Совместимость» | **Заменить** `compatibility_preview` с PR1 |

- Два человека с натальными данными (FSM партнёра)
- Доставка PDF, не только текст
- Монетизация Stars — отдельный этап после рабочего пайплайна

## Снятые противоречия

| Тема | Старый план | **Актуально** |
|------|-------------|---------------|
| Первый продукт | «я + он/она» #1 в портфеле | Полная пара + PDF (отложить «я+он/она») |
| Монетизация | После retention (backlog P3) | Бесплатный MVP совместимости, Stars позже |
| LLM | Ollama deadtiger (daily) | Облако для совместимости |
| Кнопка | Astrid A/B preview | Новый flow с PR1 |

## Инфра

- `uv sync --extra pdf` + шрифты `data/fonts/` в Docker
- Генерация PDF только в worker (не блокировать бота)
