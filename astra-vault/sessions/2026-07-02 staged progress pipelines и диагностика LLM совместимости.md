---
tags: [session, compatibility, prediction, worker, rabbitmq]
date: 2026-07-02
---

# Staged progress, пайплайны prediction/compatibility, диагностика LLM

Связано: [[пайплайн совместимости промпт LLM PDF worker]] · [[промпт совместимости синастрия JSON для LLM]] · [[Split Contract LLM и Pydantic для совместимости]]

## Сделано в коде (коммит в этой сессии)

### Staged progress (Telegram UX)
- Модуль `src/astra/telegram/progress/` — этапы, тексты Astrid, Redis `progress_message_id`, `advance_progress` + typing.
- Прогресс по кнопке (не в scheduler 09:00): удаление старого сообщения → новое + typing между этапами.

### Daily prediction — разбивка пайплайна
- Миграция `008_prediction_pipeline_status.py`: `predictions.status`, nullable `text`.
- Очереди: `natal_chart.generate` → `daily_context.build` → `prediction.generate` → `prediction.send`.
- `prediction_pipeline.py`, split `astro_service.py`, handlers в worker.

### Compatibility — разбивка пайплайна
- Статусы: `synastry_ready`, `text_ready`, `ready`, `failed`.
- Очереди: `synastry.build` → `compatibility.generate` → `pdf.generate` → `compatibility.send`.
- `compatibility_pipeline.py`, split handlers.

### RabbitMQ обязателен
- Убран `rabbitmq_enabled`; `verify_rabbitmq()` на старте API.
- Фикс publisher: не кэшировать exchange на закрытом соединении; retry publish ×1.

### Прочее
- Человекочитаемые имена PDF: `compatibility_pdf_filenames.py`.
- Удаление разборов: карточка → **Получить PDF** / **Удалить** / **К списку**.
- Тесты: progress, pipelines, publisher, delete, pdf filenames.

## Диагностика prod (deadtiger)

Симптом: после «Карты сошлись, общая картина видна 🌙» тишина; задача в `astra.compatibility` исчезает.

**Причина:** DeepSeek отвечает `200 OK`, но JSON не проходит Pydantic → `Compatibility LLM abandoned`, отчёт `failed`, уведомления юзеру нет.

Примеры из логов:
1. `working_aspects: орб 1.46 должен быть 2.0–6.0` — LLM положил аспект в неверный бакет.
2. `String should have at most 260 characters` — скорее всего `natal_insight` длиннее лимита.

Инфра (RabbitMQ, API key) в порядке — проблема **рассинхрон промпта и валидации**.

## Решение на следующую сессию

→ [[Split Contract LLM и Pydantic для совместимости]]

Рекомендация: **вариант B** — LLM отдаёт только тексты, код собирает `CompatibilityLlmOutput` (орбы, бакеты, strength, лимиты строк).

Дополнительно обсудить: retry, уведомление в TG при фейле, сохранение сырого ответа LLM.

## Не сделано

- Рефактор промпта/валидации (отложено осознанно).
- E2E на deadtiger после деплоя коммита.
- `alembic upgrade head` на сервере (если ещё не прогнали 008).
