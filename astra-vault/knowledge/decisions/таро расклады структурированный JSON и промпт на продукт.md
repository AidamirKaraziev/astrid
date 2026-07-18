---
tags: [decision, tarot, llm, architecture]
date: 2026-07-18
---

# Таро-расклады: структурированный JSON и промпт на каждый продукт

## Решение

Каждый расклад — отдельный продукт со своим промптом, Pydantic-схемой,
валидацией и форматом. Вывод модели — **структурированный JSON (поле на
позицию)**, а не свободный текст с последующим парсингом абзацев.

Пакет: `src/astra/llm/prompts/tarot_spreads/`
- `base.py` — общая персона Астрид, согласование рода, сборка запроса, парсинг
  JSON, рендер-хелперы, ABC `TarotProduct`.
- `yes_no.py` / `three_cards.py` / `relationship.py` — продукт: `system_prompt`,
  `schema`, `validate`, `render`.
- `__init__.py` — реестр `TAROT_PRODUCTS: dict[SpreadType, TarotProduct]`.

Сервис (`services/tarot_reading_service.py`): `json_mode` → `product.parse` →
`product.validate` → `product.render` (финальное HTML собирается на этапе
генерации из полей и хранится в `interpretation`; `deliver` шлёт готовое).

## Почему

Старый подход требовал ровно N+1 абзацев в строгом порядке и сшивал их с
позициями вслепую. Любое вступление модели («Aidamir, смотри…») сдвигало все
блоки на один → тексты вставали не под своими картами; «на решение» терял
вердикт. JSON с полем на позицию делает сопоставление детерминированным —
съехать нельзя. Вердикт «Да/Нет» — отдельное поле, не «угадай первое слово».

DRY: персона и согласование рода — общие в `base` (не дублируем); промпт-метод,
схема и формат — свои у каждого продукта.

## Схемы

- yes_no: `verdict / answer / summary`
- three_cards: `heart / hidden / outcome / summary` (Сердце → Скрытое → Исход)
- relationship: `you / partner / between / obstacle / direction / summary`

Имя поля схемы = `SpreadPosition.key` → `render_positioned` берёт `getattr(data,
position.key)`. `SpreadPosition.emoji` — тематическое эмодзи позиции (иначе
эмодзи карты).

## Связи

- [[таро гибридный пайплайн карты мгновенно интерпретация из worker]]
- [[sanitize прогноза схлопывал многоблочные расклады таро]]
- [[Split Contract LLM и Pydantic для совместимости]] — родственный подход
