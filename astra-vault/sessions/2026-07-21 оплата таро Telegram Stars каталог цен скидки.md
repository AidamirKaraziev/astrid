---
tags: [session, таро, оплата]
date: 2026-07-21
---

# Сессия: оплата раскладов таро в Telegram Stars + каталог цен в БД

## Цель сессии

Сделать все три расклада («Три карты», «На отношения», «Загадай желание») платными
через Telegram Stars и построить платёжную архитектуру «высшего уровня»:
мультивалютные цены и скидки в БД.

## Утверждённые продуктовые решения

- **Способ оплаты:** Telegram Stars (этап 1); карта/ЮKassa — этап 2 через внешнюю
  платёжную страницу (карточные провайдеры в боте запрещены правилами TG для цифровых товаров).
- **Модель:** все расклады платные, бесплатной осталась только «Карта дня».
  Лимит 1/день и бонусная кнопка «ещё расклад» удалены полностью.
- **Момент оплаты:** после вопроса, перед картами — пейволл в точке максимальной
  вовлечённости. Кнопка оплаты = нативный инвойс, отдельной кнопки в меню нет.
- **Цена:** в текстах не показывается, только на платёжной кнопке. Хранится в БД
  на каждый товар и валюту; фолбэк — `TAROT_READING_PRICE_STARS` из конфига.
- **Скидка (вариант B утверждён):** кнопка `5̶0̶ ⭐ → 5 ⭐ · скидка −90%`
  (юникод-зачёркивание U+0336, HTML на pay-кнопке нет) + строка с `<s>50 ⭐</s>`
  в сообщении над инвойсом.

## Схема БД (миграция 013, заменила черновики 013–015)

- `products` — справочник: `tarot_wish`, `tarot_three_cards`, `tarot_relationship`.
- `product_prices` — цена «товар × валюта» (минорные единицы: XTR=1 ⭐, RUB=копейки),
  `discount_percent`, UNIQUE(product_code, currency), CHECK amount>0 и скидка 0–99.
  Новая валюта = INSERT, без миграции.
- `payments` — самодостаточный финансовый документ: `provider + provider_charge_id`
  (UNIQUE — идемпотентность дублей successful_payment), снапшот
  `base_amount/discount_percent` на момент оплаты. FK на products с RESTRICT.
- `tarot_readings`: новый статус `pending_payment` (черновик с вопросом и картами
  до оплаты), `price_stars/paid_at` заполняются при оплате.

## Флоу оплаты

1. Кнопка расклада → вопрос (FSM, без проверки лимита).
2. Черновик `pending_payment` в БД (переживает рестарт) → `answer_invoice`
   (payload `tarot:<uuid>`).
3. `pre_checkout` валидирует черновик (существует, не оплачен).
4. `successful_payment` → Payment со снапшотом → `mark_reading_paid` → карты
   альбомом → `publish_tarot_reading_generate`. Гонки дублей ловятся уникальным
   индексом + IntegrityError rollback.
5. Worker не берёт неоплаченные черновики; при финальном фейле LLM —
   **авто-refund** (`refundStarPayment`) + текст «звёзды вернулись».
6. Осиротевший платёж (черновик не найден) рефандится сразу в хендлере.
7. `/paysupport` (обязателен для Stars-ботов) добавлен в команды и Menu Button.

## Код

- Новый модуль `src/astra/payments/` (enums, models+crud, service).
- `tarot_spreads.py` перестроен: инвойс после вопроса, pre_checkout,
  successful_payment, legacy-хендлер старой кнопки «ещё расклад».
- Снапшот при регистрации платежа: если каталог сходится с фактом — берём
  base/discount из каталога; если цена изменилась между инвойсом и оплатой —
  факт важнее (base=уплачено, скидка 0).
- 426 тестов зелёные.

## Починка локальной БД

Локально была применена удалённая миграция 014 → alembic падал
«Can't locate revision». Решение: DROP старых payments/product_prices,
`UPDATE alembic_version SET version_num='012'`, `alembic upgrade head`.
На проде проблемы нет — там миграции ≥013 не применялись.

## Управление ценами (шпаргалка)

```sql
UPDATE product_prices SET amount = 75 WHERE product_code = 'tarot_wish' AND currency = 'XTR';
UPDATE product_prices SET discount_percent = 90 WHERE product_code = 'tarot_relationship' AND currency = 'XTR';
INSERT INTO product_prices (id, product_code, currency, amount, discount_percent, is_active)
VALUES (gen_random_uuid(), 'tarot_wish', 'RUB', 19900, 0, true);
```

## Осталось

- Живой E2E с реальной оплатой Stars (инвойс нельзя оплатить тестово) + проверить
  рендер юникод-зачёркивания на реальных устройствах (старые Android — риск).
- `alembic upgrade head` на проде (накатит 012 + 013) и push веток.
- Задать `TELEGRAM_SUPPORT_USERNAME` в prod `.env` — используется в `/paysupport`.

## Связанные заметки

- [[цены и скидки товаров в БД каталог товар на валюту со снапшотом в платеже]]
- [[таро гибридный пайплайн карты мгновенно интерпретация из worker]]
- [[2026-07-19 таро замена На решение на Загадай желание]]
