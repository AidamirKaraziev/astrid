"""Команды, Menu Button и то, что человек читает до первого сообщения."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonCommands

from astra.core.observability import Event, get_logger

log = get_logger(__name__)

BOT_COMMANDS_RU: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="help", description="💬 Помощь и поддержка"),
    BotCommand(command="paysupport", description="⭐ Поддержка по оплате"),
)

# Строка под именем бота в его профиле. До 120 знаков, разметки нет.
SHORT_DESCRIPTION = (
    "Астролог, которая говорит по-человечески: карта дня, расклады таро "
    "и разбор натальной карты ✨"
)

# Пустой чат до нажатия «Начать»: единственный экран, который видит человек,
# пришедший из рекламы. Разметка здесь не работает вообще, поэтому структуру
# держат абзацы. Задача текста одна — объяснить, что будет после кнопки.
DESCRIPTION = (
    "Привет, я Астрид — твой астролог.\n\n"
    "Каждое утро смотрю, что происходит в небе, и рассказываю по-человечески: "
    "где сегодня попутный ветер, а где лучше притормозить.\n\n"
    "Карта дня — бесплатно. Расклады таро, разбор натальной карты и "
    "совместимость — когда захочешь заглянуть глубже.\n\n"
    "Нажми «Начать» — познакомимся ✨"
)


async def setup_bot_menu(bot: Bot) -> None:
    """Регистрирует команды, Menu Button и описания бота.

    Описания ставим без `language_code`: это значение по умолчанию, его видят
    все клиенты. Аудитория русскоязычная, а пустой первый экран у человека с
    английским интерфейсом — потеря на ровном месте.
    """
    await bot.set_my_commands(list(BOT_COMMANDS_RU), language_code="ru")
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await bot.set_my_short_description(short_description=SHORT_DESCRIPTION)
    await bot.set_my_description(description=DESCRIPTION)
    log.info(Event.TELEGRAM_BOT_MENU_CONFIGURED, commands_count=len(BOT_COMMANDS_RU))
