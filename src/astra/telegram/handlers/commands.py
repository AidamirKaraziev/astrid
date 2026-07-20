"""Slash-команды из Menu Button."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from astra.core.config import get_settings
from astra.telegram.handlers.catalog import show_help

router = Router(name="commands")

_PAYSUPPORT_TEXT = (
    "⭐ <b>Поддержка по оплате</b>\n\n"
    "Расклады таро оплачиваются в Telegram Stars. Если интерпретация не пришла, "
    "звёзды возвращаются автоматически.\n\n"
    "Если что-то пошло не так с оплатой — напиши нам{support}, разберёмся и вернём звёзды."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await show_help(message)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    """Обязательная команда для ботов с платежами Stars (правила Telegram)."""
    username = get_settings().telegram_support_username.strip().lstrip("@")
    support = f": @{username}" if username else " через /help"
    await message.answer(_PAYSUPPORT_TEXT.format(support=support), parse_mode="HTML")
