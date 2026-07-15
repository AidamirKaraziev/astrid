---
tags: [decision, tarot, architecture]
date: 2026-07-16
---

# Таро: гибридный пайплайн — карты мгновенно, интерпретация из worker

## Решение

Платные расклады (ветка `feature/tarot-track`) работают гибридно:

1. **Бот (мгновенно):** лимит-чек → `draw_cards()` → строка `tarot_readings` →
   **commit** → фото карт (одна — `send_card_photo`, расклад — альбом
   `send_cards_album`) → publish `tarot_reading.generate`.
2. **Worker:** LLM-интерпретация (DeepSeek, 2 попытки, блочная валидация) →
   `tarot_reading.send` → текст через `send_telegram_html`.

LLM в хендлерах aiogram не вызывается никогда (таймаут DeepSeek до 120 сек).
Карта дня (`tarot_daily_service`) осталась на старом инлайн-пути — grandfathered.

## Почему так

- Пользователь получает «карты легли» мгновенно — ритуал не ждёт LLM.
- Resumability по статусу (`pending → generating → text_ready → ready/failed`),
  как у совместимости: рестарт worker посреди генерации не теряет заказ.
- Фото шлёт только бот (aiogram + кэш file_id, паттерн welcome-видео) —
  worker-у не нужен код отправки медиа.
- Порядок жёсткий: **commit до publish** (грабли [[RabbitMQ send раньше commit generate и отсутствие socksio]]).

## Ключевые файлы

- `src/astra/tarot/spreads.py` — спеки раскладов (позиции + смыслы) = источник
  правды для промпта, валидации и форматирования.
- `src/astra/services/tarot_reading_service.py` — лимит/создание/генерация/доставка.
- `src/astra/llm/prompts/tarot_spread.py` — блок на позицию + «Итог»;
  для «Да/Нет» итог обязан начинаться с «Да»/«Нет».
- `src/astra/telegram/handlers/tarot_spreads.py` — FSM: один state
  `TarotStates.waiting_question`, тип расклада в FSM data.
- Миграция `012_tarot_readings` — `price_stars`/`paid_at` nullable: Stars
  подключаются без миграции.

## Лимиты

1 расклад/день (`tarot_spreads_daily_limit`), счёт по БД (failed не считается —
попытка возвращается), Redis NX-лок от даблтапа. Сообщение лимита — крючок
под будущую монетизацию.

## Связи

- [[кэш file_id вместо повторной заливки медиа в Telegram]]
- [[пайплайн совместимости промпт LLM PDF worker]] — образец пайплайна
- [[портфель монетизации Astra]] — продукты #16–18
