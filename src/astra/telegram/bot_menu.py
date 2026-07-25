"""Команды бота и Menu Button (кнопка «Меню» слева от поля ввода)."""

from __future__ import annotations

from astra.core.observability import Event, get_logger
from aiogram.types import BotCommand, MenuButtonCommands

log = get_logger(__name__)

BOT_COMMANDS_RU: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="help", description="💬 Помощь и поддержка"),
    BotCommand(command="paysupport", description="⭐ Поддержка по оплате"),
)


async def setup_bot_menu(bot: Bot) -> None:
    """Регистрирует команды и включает Menu Button со списком команд."""
    await bot.set_my_commands(list(BOT_COMMANDS_RU), language_code="ru")
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    log.info(Event.TELEGRAM_BOT_MENU_CONFIGURED, commands_count=len(BOT_COMMANDS_RU))
