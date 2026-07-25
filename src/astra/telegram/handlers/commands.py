"""Slash-команды из Menu Button: помощь и обязательный /paysupport."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from astra.core.config import get_settings
from astra.telegram import support_text as T
from astra.telegram.button_texts import SUPPORT_FAQ_PAYMENT
from astra.telegram.handlers.support import can_reach_human, open_support_hub
from astra.telegram.keyboards import support_faq_keyboard

router = Router(name="commands")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Хаб службы заботы: FAQ + живой оператор."""
    await open_support_hub(message)


@router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    """Служебная: показать chat_id (для настройки TELEGRAM_ADMIN_GROUP_ID).

    Работает и в группах — команды приходят боту даже при включённом privacy
    mode. В группе можно написать `/chatid@daily_astrid_bot`.
    """
    await message.answer(
        f"chat_id: <code>{message.chat.id}</code>\ntype: {message.chat.type}",
    )


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    """Обязательная команда для ботов с платежами Stars (правила Telegram).

    Открываем сразу ветку про оплату и возврат звёзд.
    """
    settings = get_settings()
    await message.answer(
        T.FAQ_ANSWERS[SUPPORT_FAQ_PAYMENT],
        reply_markup=support_faq_keyboard(can_reach_human(settings)),
    )
