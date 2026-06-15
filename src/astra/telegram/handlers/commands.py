"""Slash-команды из Menu Button."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from astra.telegram.handlers.catalog import show_help

router = Router(name="commands")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await show_help(message)
