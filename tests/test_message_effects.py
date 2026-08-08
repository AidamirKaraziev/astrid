"""Эффекты сообщений, реакции бота и описания бота до первого сообщения."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendMessage
from aiogram.types import ReactionTypeEmoji

from astra.broadcasts.editor import check
from astra.telegram.bot_menu import DESCRIPTION, SHORT_DESCRIPTION, setup_bot_menu
from astra.telegram.effects import EFFECT_CELEBRATION, send_with_effect
from astra.telegram.screen import react


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=SendMessage(chat_id=1, text="x"),
        message=text,
    )


class TestEffects:
    async def test_effect_is_passed_to_telegram(self) -> None:
        send = AsyncMock(return_value="sent")

        result = await send_with_effect(send, "фото", effect=EFFECT_CELEBRATION, caption="карты")

        assert result == "sent"
        send.assert_awaited_once_with(
            "фото",
            message_effect_id=EFFECT_CELEBRATION,
            caption="карты",
        )

    async def test_no_effect_means_plain_call(self) -> None:
        send = AsyncMock()

        await send_with_effect(send, "фото", effect=None, caption="карты")

        send.assert_awaited_once_with("фото", caption="карты")

    async def test_rejected_effect_still_delivers_the_message(self) -> None:
        """Официального списка id у эффектов нет — украшение не смеет съесть оплаченное."""
        send = AsyncMock(side_effect=[_bad_request("Bad Request: EFFECT_INVALID"), "sent"])

        result = await send_with_effect(send, "фото", effect="1", caption="карты")

        assert result == "sent"
        assert send.await_count == 2
        assert "message_effect_id" not in send.await_args.kwargs  # повтор без эффекта


class TestReaction:
    async def test_sets_emoji_on_the_message(self) -> None:
        message = MagicMock()
        message.react = AsyncMock()

        await react(message, "👀")

        message.react.assert_awaited_once_with([ReactionTypeEmoji(emoji="👀")])

    @pytest.mark.parametrize(
        "error",
        [
            _bad_request("Bad Request: REACTION_INVALID"),
            TelegramNetworkError(method=SendMessage(chat_id=1, text="x"), message="timeout"),
        ],
    )
    async def test_failure_never_breaks_the_scenario(self, error: Exception) -> None:
        """Сразу после реакции создаётся платный черновик — икота на украшении не в счёт."""
        message = MagicMock()
        message.react = AsyncMock(side_effect=error)

        await react(message, "👀")  # не должно бросить


class TestExpandableQuote:
    def test_sanitizer_accepts_expandable_blockquote(self) -> None:
        """Длинный разбор сворачивается в цитату — проверка разметки этому не мешает."""
        assert check("<blockquote expandable>Длинный кусок текста.</blockquote>") == ()


class TestBotDescriptions:
    def test_fit_telegram_limits(self) -> None:
        assert len(SHORT_DESCRIPTION) <= 120
        assert len(DESCRIPTION) <= 512

    def test_speak_as_astrid_without_markup(self) -> None:
        """На этом экране разметка не работает вообще, а «Astra» — имя проекта."""
        assert "Астрид" in DESCRIPTION
        assert "Astra" not in DESCRIPTION and "Astra" not in SHORT_DESCRIPTION
        assert "<" not in DESCRIPTION and "<" not in SHORT_DESCRIPTION

    async def test_setup_registers_commands_and_descriptions(self) -> None:
        bot = MagicMock()
        bot.set_my_commands = AsyncMock()
        bot.set_chat_menu_button = AsyncMock()
        bot.set_my_short_description = AsyncMock()
        bot.set_my_description = AsyncMock()

        await setup_bot_menu(bot)

        bot.set_my_short_description.assert_awaited_once_with(
            short_description=SHORT_DESCRIPTION,
        )
        bot.set_my_description.assert_awaited_once_with(description=DESCRIPTION)
