---
tags: [session, telegram, ux, menu]
date: 2026-06-15
---

# Сессия 2026-06-15 — UX меню бота, платные продукты, Menu Button

Ветка: `feature/bot-catalog-menu` (не закоммичено на момент сохранения).

## Сделано

### Главное меню (reply)

Финальная раскладка **вариант B**:

```
[ 🔮 Предсказание на сегодня ]
[ 💕 Совместимость ] [ 🌌 Разбор натала ]
[ 📅 Прогноз на месяц ] [ 🔮 Карты Таро ]
[ ✨ Обо мне ] [ 🎁 Пригласить друга ]
```

- Убраны: **💫 Каталог**, **✉️ Помощь**, **🌟 Спросить звёзды** (из reply).
- **✨ Обо мне** вместо «👤 Профиль».
- Платные продукты — заглушка «Скоро появится, выбери что-то другое.»
- **🔮 Карты Таро** → подменю (3 расклада + ◀️ В меню).

Константы: `src/astra/telegram/button_texts.py`.

### Автообновление reply-меню

- `AutoKeyboardMiddleware` — подставляет актуальную клавиатуру, если хендлер не задал `reply_markup`.
- `keyboard_policy.py` — зоны MAIN / TAROT.
- `send_prediction_to_telegram()` — пуш и worker шлют прогноз с inline CTA.

См. [[reply-меню Telegram обновляется через AutoKeyboardMiddleware]].

### Menu Button (slash-команды)

Финал:

| Команда | Описание в меню |
|---------|-----------------|
| `/start` | 🏠 Главное меню |
| `/help` | 💌 Написать Astrid |

- `/start` и `/menu` — один хендлер: незарегистрированный → онбординг; зарегистрированный → «Главное меню ✨» + клавиатура (без длинного приветствия).
- `/help` — карточка «что умеет бот» + inline **💌 Написать Astrid** (`help_text.py`, `help_keyboard()`).
- Настройка при старте: `configure_telegram_bot()` → `bot_menu.py`.

### Inline под прогнозом

- Кнопка **🌟 Спросить звёзды** (`style=primary`) под каждым прогнозом.
- `callback_data=product:ask_stars` → заглушка.

### Конфиг

- `TELEGRAM_SUPPORT_USERNAME` — для `/help` (`.env.example`).

### Тесты

88 тестов: `test_catalog_keyboards`, `test_keyboard_policy`, `test_auto_keyboard_middleware`, `test_bot_menu_and_prediction_cta`.

## Файлы (ключевые)

- `src/astra/telegram/button_texts.py`
- `src/astra/telegram/keyboards.py`
- `src/astra/telegram/handlers/catalog.py` (продукты + help)
- `src/astra/telegram/handlers/commands.py`
- `src/astra/telegram/handlers/start.py`
- `src/astra/telegram/auto_keyboard_middleware.py`
- `src/astra/telegram/keyboard_policy.py`
- `src/astra/telegram/bot_menu.py`
- `src/astra/telegram/help_text.py`

## Не сделано / следующий шаг

- Коммит и merge ветки `feature/bot-catalog-menu`.
- E2E на deadtiger + TG с новым меню.
- Реальная логика платных продуктов и оплата (P3).
- `TELEGRAM_SUPPORT_USERNAME` — задать в `.env` на сервере.
- Mini App для витрины — позже.

## Связи

- [[reply-меню Telegram обновляется через AutoKeyboardMiddleware]]
- [[главное меню бота платные продукты в reply без каталога]]
- [[продукт Astra telegram предсказания RU аудитория]]
- [[портфель монетизации Astra]]
