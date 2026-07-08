---
tags: [decision, llm, ollama, deepseek, infra]
date: 2026-07-08
status: утверждено
---

# Локальная LLM (Ollama) удалена, весь daily на DeepSeek

Связано: [[пайплайн совместимости промпт LLM PDF worker]] · [[промпт Astrid v3 — вопрос дня gemma4 e2b]] (legacy) · [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]

## Решение

Полный отказ от локально развёрнутой LLM (Ollama, `gemma4:e2b` на deadtiger). Все генерации — облачный **DeepSeek**: ежедневные прогнозы (Astrid v4), таро дня, зодиак-гороскопы, совместимость, натал. Переключатель `DAILY_LLM_PROVIDER` удалён — жёстко DeepSeek (решение Аида, 2026-07-08). Legacy-путь Astrid v3 (Ollama-only) удалён целиком, остался только v4.

## Что удалено

- `src/astra/llm/local/` (OllamaProvider), `src/astra/llm/ollama.py`, `src/astra/llm/astrid_generate.py`, `src/astra/llm/warmup.py`, `src/astra/llm/prompts/astrid_checklist.py`
- v3-билдеры промпта из `prompts/astrid.py` (архетипы, sanitize/validate остались — их использует v4)
- Мёртвые v3-функции из `astro_service.py`; legacy v1-контекст теперь даёт явный reason `legacy_context`
- Скрипты `smoke_astrid_v3.py`, `e2e_astrid_v3.py`
- Конфиг: поля `ollama_*` и `daily_llm_provider` из Settings, блоки из `.env.example`
- docker-compose: сервисы `ollama`, `ollama-init`, volume `ollama_data`, `depends_on` у worker
- События `OLLAMA_WARMUP_*` → вместо warmup worker при старте проверяет `daily_provider_enabled` и пишет `llm.daily_provider_unconfigured` (fail-loud, чтобы daily не умирал молча)

## Архитектура после

- Фичи знают только `BaseLlmProvider` + `get_daily_provider()` / `daily_provider_enabled()` из `llm/daily_llm.py` (DIP) — смена облачного провайдера в будущем = правка одного модуля.
- Sentry-теги сбоев генерации: `llm_provider` / `llm_model` (вместо `ollama_model`).
- Тексты причин ошибок нейтральные («таймаут LLM»).

## Ручные шаги на deadtiger (деплой)

1. До `git pull`: в prod `.env` проверить `DEEPSEEK_ENABLED=true`, `DEEPSEEK_API_KEY`; строки `OLLAMA_*`/`DAILY_LLM_PROVIDER` удалить (безвредны: `extra="ignore"`).
2. `git pull && docker compose up -d --build --remove-orphans` — снесёт контейнеры ollama.
3. `docker volume rm astra_ollama_data` (несколько ГБ модели), `docker image rm ollama/ollama:latest`.
4. Проверить: логи worker (нет warmup, нет `llm.daily_provider_unconfigured`), тестовое предсказание/карта дня, Sentry-тег `llm_provider=deepseek`.

## Риски

- `DEEPSEEK_API_KEY` не задан → daily уходит в 15 ретраев и FAILED; ловится warning-событием при старте worker и Sentry.
- Стоимость/лимиты DeepSeek на daily-объёме — мониторить `llm.http_error` `http_429`.
