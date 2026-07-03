"""Уведомление в Telegram при фейле генерации совместимости."""

from __future__ import annotations

from astra.core.observability import Event, get_logger
from astra.workers.telegram_send import send_telegram_html

log = get_logger(__name__)

COMPATIBILITY_FAILURE_TEXT = (
    "Не получилось составить разбор совместимости — произошла ошибка.\n"
    "Попробуй заказать анализ ещё раз через 💕 <b>Совместимость</b>."
)


async def send_compatibility_failure_notification(telegram_id: int) -> None:
    try:
        await send_telegram_html(telegram_id, COMPATIBILITY_FAILURE_TEXT)
    except Exception:
        log.exception(
            Event.COMPATIBILITY_NOTIFY_FAILED,
            telegram_id=telegram_id,
        )
