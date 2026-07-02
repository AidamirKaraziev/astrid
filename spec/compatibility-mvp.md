# Совместимость MVP (2026-06-26)

## UX

1. `💕 Совместимость`
2. Контекст: отношения / работа / дружба
3. Режим: «Я + он/она» | «Он + она»
4. FSM сбора данных (время опционально, «⏭ Пропустить»)
5. Подтверждение → worker → PDF в Telegram
6. История: кнопка в «✨ Обо мне» → список → переслать PDF

## Продуктовые решения

| Решение | Выбор |
|---------|--------|
| Доставка | Только PDF |
| LLM | DeepSeek |
| Хранение PDF | Volume (`COMPATIBILITY_PDF_DIR`) |
| NatalProfile | Автосохранение по имени |
| Дубликаты | Всегда новый разбор |
| Лимиты | Нет |
| «Для других» | Совместимость + NatalProfile (без daily в MVP) |

## Данные

- `natal_profiles` — карточки людей (owner_user_id)
- `compatibility_reports` — заказы: контекст, режим, snapshots, llm_output, pdf_path, status

## Worker

`compatibility.generate` → synastry → DeepSeek JSON → mapper → PDF → sendDocument
