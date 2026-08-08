"""Контракт отправки: что остаётся в чате навсегда, а что живёт до следующего шага.

Три вида исходящих сообщений, и каждый хендлер обязан выбрать один:

* **контент** (`send_content`) — прогноз, расклад, ответ Астрид, PDF. Всегда
  новое сообщение: оно поднимает чат наверх и даёт уведомление. Остаётся.
* **экран** (`show_screen`) — меню, вопрос сценария, подсказка, прогресс. Одно
  сообщение на раздел, которое переписывается на каждом шаге. Исчезает.
* **тост** (`toast` / `alert`) — подтверждение нажатия. В историю не попадает
  вообще, поэтому в него нельзя класть то, что человек захочет перечитать.
* **реакция** (`react`) — ответ на сообщение человека вообще без сообщения:
  бот ставит 👀 на присланный вопрос вместо реплики «приняла».

Экран привязан к паре «чат + `scope`»: у таро свой экран, у колеса свой, и они
не затирают друг друга. `scope` — короткая строка вроде `"tarot"`.

Два ограничения Telegram, ради которых этот модуль и существует:

* сообщение старше 48 часов не редактируется, а удалённое человеком — тем
  более; на любой отказ редактирования экран пересоздаётся, а не роняет
  сценарий;
* текстовое сообщение не превращается в медиа и обратно — при смене типа
  старый экран удаляется и отправляется новый.

Контент уходит через `message.answer`, чтобы `AutoKeyboardMiddleware` доложил
актуальную reply-клавиатуру. Экран — всегда через `bot`, мимо middleware:
reply-клавиатура и inline-кнопки живут в одном поле `reply_markup`, и экран это
поле занимает своими кнопками.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMedia,
    Message,
    ReactionTypeEmoji,
)

from astra.core.observability import Event, get_logger
from astra.telegram.screen_store import (
    Screen,
    ScreenKind,
    clear_screen,
    get_screen,
    set_screen,
)

log = get_logger(__name__)

# Telegram обрезает текст ответа на callback по 200 символам.
_CALLBACK_TEXT_LIMIT = 200

Event_ = Message | CallbackQuery


def _bot_and_chat(event: Event_) -> tuple[Bot, int] | None:
    """Бот и чат из апдейта; None — отправлять некуда."""
    message = event if isinstance(event, Message) else event.message
    if not isinstance(message, Message):
        return None
    bot = message.bot
    if bot is None:
        return None
    return bot, message.chat.id


def _message_of(event: Event_) -> Message | None:
    message = event if isinstance(event, Message) else event.message
    return message if isinstance(message, Message) else None


def _is_human_message(event: Event_) -> bool:
    """Апдейт пришёл от человека, а не с кнопки на сообщении бота."""
    if not isinstance(event, Message):
        return False
    return event.from_user is not None and not event.from_user.is_bot


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


def _is_unreachable(exc: TelegramBadRequest) -> bool:
    """Сообщение уже нельзя тронуть: удалено, слишком старое или чужое."""
    text = str(exc).lower()
    return any(
        fragment in text
        for fragment in (
            "message to edit not found",
            "message can't be edited",
            "message to delete not found",
            "message_id_invalid",
        )
    )


async def _screen_to_edit(
    event: Event_,
    chat_id: int,
    scope: str,
    *,
    keep_position: bool,
) -> Screen | None:
    """Экран, который можно переписать на месте. None — нужен новый, внизу чата.

    Правка на месте верна ровно тогда, когда человек смотрит на сам экран, то
    есть пришёл с кнопки на нём. Если он написал текстом или нажал
    reply-кнопку, его сообщение уже ниже экрана — а между ними мог оказаться
    инвойс или карты. Экран уехал бы наверх, и человек решил бы, что раздел
    не работает. Поэтому переносим экран вниз, к последнему сообщению.

    `keep_position` отменяет перенос: несколько подряд идущих кадров одного и
    того же экрана (анимация колеса) приходят с одним апдейтом человека, и
    переносить его на каждом кадре было бы мельтешением.
    """
    screen = await get_screen(chat_id, scope)
    if screen is None:
        return None
    if keep_position or not _is_human_message(event):
        return screen
    await close_screen(event, scope)
    return None


async def send_content(
    event: Event_,
    text: str,
    *,
    scope: str | None = None,
    **kwargs: Any,
) -> Message | None:
    """Отправить то, что остаётся в чате навсегда.

    `scope` — погасить экран этого раздела перед выдачей: результат не должен
    выезжать из-под живого меню.
    """
    message = _message_of(event)
    if message is None:
        return None
    if scope is not None:
        await close_screen(event, scope)
    return await message.answer(text, **kwargs)


async def show_screen(
    event: Event_,
    text: str,
    *,
    scope: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    keep_position: bool = False,
    **kwargs: Any,
) -> int | None:
    """Показать или обновить живой экран раздела. Возвращает его message_id.

    `keep_position` — продолжение уже стоящего экрана (кадр анимации): править
    строго на месте, вниз не переносить.
    """
    resolved = _bot_and_chat(event)
    if resolved is None:
        return None
    bot, chat_id = resolved

    screen = await _screen_to_edit(event, chat_id, scope, keep_position=keep_position)
    if screen is not None and screen.kind is ScreenKind.TEXT:
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=screen.message_id,
                reply_markup=reply_markup,
                **kwargs,
            )
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return screen.message_id
            if not _is_unreachable(exc):
                raise
            log.debug(
                Event.TELEGRAM_SCREEN_RECREATED,
                chat_id=chat_id,
                scope=scope,
                message_id=screen.message_id,
                reason=str(exc),
            )
        else:
            return screen.message_id
    elif screen is not None:
        # Экран был медийным: превратить фото в текст Telegram не даёт.
        await close_screen(event, scope)

    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
    await set_screen(chat_id, scope, sent.message_id, ScreenKind.TEXT)
    return sent.message_id


async def show_media_screen(
    event: Event_,
    media: InputMedia,
    *,
    scope: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    keep_position: bool = False,
) -> int | None:
    """То же, что `show_screen`, но экран — картинка с подписью."""
    resolved = _bot_and_chat(event)
    if resolved is None:
        return None
    bot, chat_id = resolved

    screen = await _screen_to_edit(event, chat_id, scope, keep_position=keep_position)
    if screen is not None and screen.kind is ScreenKind.MEDIA:
        try:
            await bot.edit_message_media(
                media=media,
                chat_id=chat_id,
                message_id=screen.message_id,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return screen.message_id
            if not _is_unreachable(exc):
                raise
            log.debug(
                Event.TELEGRAM_SCREEN_RECREATED,
                chat_id=chat_id,
                scope=scope,
                message_id=screen.message_id,
                reason=str(exc),
            )
        else:
            return screen.message_id
    elif screen is not None:
        await close_screen(event, scope)

    sent = await bot.send_photo(
        chat_id,
        media.media,
        caption=media.caption,
        reply_markup=reply_markup,
    )
    await set_screen(chat_id, scope, sent.message_id, ScreenKind.MEDIA)
    return sent.message_id


async def close_screen(event: Event_, scope: str) -> None:
    """Убрать экран раздела из чата и из реестра."""
    resolved = _bot_and_chat(event)
    if resolved is None:
        return
    bot, chat_id = resolved

    screen = await clear_screen(chat_id, scope)
    if screen is None:
        return
    try:
        await bot.delete_message(chat_id, screen.message_id)
    except TelegramBadRequest as exc:
        if not _is_unreachable(exc):
            raise


async def toast(callback: CallbackQuery, text: str = "") -> None:
    """Плашка сверху: подтверждает то, что человек и так понял."""
    await callback.answer(text[:_CALLBACK_TEXT_LIMIT])


async def alert(callback: CallbackQuery, text: str) -> None:
    """Модалка с «ОК»: человек хотел одного, а сначала нужно другое."""
    await callback.answer(text[:_CALLBACK_TEXT_LIMIT], show_alert=True)


async def react(message: Message, emoji: str) -> None:
    """Поставить реакцию на сообщение человека вместо ответа «приняла».

    Тихая функция: реакция — знак внимания, и её отказ не должен ломать
    сценарий. Ловим весь `TelegramAPIError`, а не только `BadRequest`: сразу
    после реакции идёт создание платного черновика, и сетевая икота на
    украшении не имеет права отменить покупку.
    """
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramAPIError as exc:
        log.debug(Event.TELEGRAM_API_FAILED, method="setMessageReaction", reason=str(exc))


__all__ = [
    "alert",
    "close_screen",
    "react",
    "send_content",
    "show_media_screen",
    "show_screen",
    "toast",
]
