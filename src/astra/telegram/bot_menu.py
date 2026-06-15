"""Команды бота и Menu Button (кнопка «Меню» слева от поля ввода)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands

logger = logging.getLogger(__name__)

BOT_COMMANDS_RU: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="help", description="💌 Написать Astrid"),
)


async def setup_bot_menu(bot: Bot) -> None:
    """Регистрирует команды и включает Menu Button со списком команд."""
    await bot.set_my_commands(list(BOT_COMMANDS_RU), language_code="ru")
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Telegram bot menu: %s commands, MenuButton=commands", len(BOT_COMMANDS_RU))
