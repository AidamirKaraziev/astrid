"""Уведомление в Telegram при фейле генерации разбора натала."""

from __future__ import annotations

from astra.core.observability import Event, get_logger
from astra.workers.telegram_send import send_telegram_html

log = get_logger(__name__)

NATAL_FAILURE_TEXT = (
    "Не получилось составить разбор натальной карты — произошла ошибка.\n"
    "Попробуй заказать разбор ещё раз через 🌌 <b>Разбор натала</b>."
)


async def send_natal_failure_notification(telegram_id: int) -> None:
    try:
        await send_telegram_html(telegram_id, NATAL_FAILURE_TEXT)
    except Exception:
        log.exception(
            Event.NATAL_REPORT_NOTIFY_FAILED,
            telegram_id=telegram_id,
        )
