---
tags: [pattern, telegram, ux]
date: 2026-06-15
---

# Reply-меню Telegram обновляется через AutoKeyboardMiddleware

## Проблема

Reply-клавиатура **кэшируется в клиенте** Telegram. После деплоя с новыми кнопками пользователь видит старое меню, пока бот снова не пришлёт `reply_markup`.

## Решение

1. **`AutoKeyboardMiddleware`** — патчит `message.answer()`: если `reply_markup` не задан, подставляет клавиатуру по зоне (`keyboard_policy.py`).
2. **Исходящие вне хендлеров** — `send_telegram_html()` / `send_prediction_to_telegram()` с `keyboard_zone=MAIN` или inline для прогноза.
3. **Исключения** — онбординг, поиск города (FSM), явный `reply_markup` в хендлере.

## Зоны

| Зона | Когда | Клавиатура |
|------|-------|------------|
| MAIN | по умолчанию | `main_menu_keyboard()` |
| TAROT | таро-кнопки | `tarot_keyboard()` |
| — | FSM онбординг / places | не подставлять |

## Ограничение API

Inline-кнопки и reply в **одном** сообщении нельзя. Прогноз с inline CTA не обновляет reply внизу — обновится при следующем reply-ответе или пуше с клавиатурой.

## Код

- `src/astra/telegram/auto_keyboard_middleware.py`
- `src/astra/telegram/keyboard_policy.py`
- `src/astra/workers/telegram_send.py`

## Связи

- [[главное меню бота платные продукты в reply без каталога]]
- [[2026-06-15 UX меню бота платные продукты Menu Button]]
