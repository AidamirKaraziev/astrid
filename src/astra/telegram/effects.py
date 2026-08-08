"""Эффекты сообщений: анимация поверх сообщения в личном чате.

Telegram проигрывает конфетти или огонь над сообщением, если передать
`message_effect_id`. Работает только в личных чатах — у нас все чаты личные.

Официального списка идентификаторов Telegram не публикует: эффекты видны в
клиенте, а их id ходят по сообществу. Отсюда главное правило этого модуля —
**эффект не имеет права уронить доставку**. Он украшение; если Telegram не
примет id, человек всё равно должен получить то, за что заплатил. Поэтому
любая отправка идёт через `send_with_effect`, который на отказ повторяет вызов
без эффекта.

Здесь только три id, которые доступны без Premium и проверены на живом боте.
Добавлять новые — с той же проверкой, а не «нашёл в интернете».
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiogram.exceptions import TelegramBadRequest

from astra.core.observability import Event, get_logger

log = get_logger(__name__)

EFFECT_CELEBRATION = "5046509860389126442"  # 🎉
EFFECT_FIRE = "5104841245755180586"  # 🔥
EFFECT_HEART = "5159385139981059251"  # ❤️

T = TypeVar("T")


async def send_with_effect(
    send: Callable[..., Awaitable[T]],
    *args: Any,
    effect: str | None,
    **kwargs: Any,
) -> T:
    """Отправить с эффектом; если Telegram его не принял — то же самое без него.

    `send` — любой метод отправки aiogram, понимающий `message_effect_id`:
    `answer`, `answer_photo`, `answer_media_group`.
    """
    if effect is None:
        return await send(*args, **kwargs)
    try:
        return await send(*args, message_effect_id=effect, **kwargs)
    except TelegramBadRequest as exc:
        log.info(Event.TELEGRAM_EFFECT_REJECTED, effect=effect, reason=str(exc))
        return await send(*args, **kwargs)


__all__ = [
    "EFFECT_CELEBRATION",
    "EFFECT_FIRE",
    "EFFECT_HEART",
    "send_with_effect",
]
