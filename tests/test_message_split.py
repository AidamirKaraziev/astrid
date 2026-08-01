"""Длинный разбор уходит несколькими сообщениями, а не падает с 400.

Telegram отвечает `400 Bad Request: message is too long` на текст длиннее
4096 знаков. У «судьбоносных партнёров» объём растёт с числом партнёров, и
верхней границы нет ни в схеме ответа, ни в промпте.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from astra.telegram.message_split import TELEGRAM_MESSAGE_LIMIT, split_html_message


def test_short_text_stays_one_message() -> None:
    assert split_html_message("привет") == ["привет"]


def test_exactly_at_the_limit_is_not_split() -> None:
    text = "a" * TELEGRAM_MESSAGE_LIMIT
    assert split_html_message(text) == [text]


def test_every_part_fits_the_limit() -> None:
    block = "<b>Партнёр</b>\nдлинный портрет на много слов подряд\n\n"
    text = block * 300

    parts = split_html_message(text)

    assert len(parts) > 1
    assert all(len(part) <= TELEGRAM_MESSAGE_LIMIT for part in parts)


def test_nothing_is_lost() -> None:
    """Хвост платного разбора — итог и действие; терять его нельзя."""
    text = "\n\n".join(f"блок {number} " + "х" * 200 for number in range(60))

    parts = split_html_message(text)

    # содержимое то же, отличаться могут только пробелы на швах
    assert "".join(" ".join(parts).split()) == "".join(text.split())
    assert "блок 59" in parts[-1]


def test_split_happens_on_blank_lines() -> None:
    """Блок разбора не должен разрываться посередине."""
    block = "<b>Заголовок</b>\nтекст блока\n\n"
    parts = split_html_message(block * 200)

    for part in parts:
        assert part.count("<b>") == part.count("</b>")
        assert not part.startswith("текст блока")


def test_falls_back_to_single_newline_without_blank_lines() -> None:
    parts = split_html_message("\n".join("строка " + "я" * 100 for _ in range(80)))

    assert all(len(part) <= TELEGRAM_MESSAGE_LIMIT for part in parts)
    assert len(parts) > 1


def test_hard_cut_never_splits_a_tag() -> None:
    """Сплошная простыня без переводов строк — режем, но не посреди тега."""
    text = "я" * (TELEGRAM_MESSAGE_LIMIT - 3) + "<b>хвост</b>" + "я" * 200

    parts = split_html_message(text)

    assert all("<b" not in part or "<b>" in part for part in parts)
    assert all(len(part) <= TELEGRAM_MESSAGE_LIMIT for part in parts)


@pytest.mark.anyio
async def test_long_answer_is_sent_in_parts_with_one_keyboard() -> None:
    from astra.workers.telegram_send import send_telegram_html

    sent: list[dict] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url: str, json: dict):  # noqa: A002
            sent.append(json)
            return httpx.Response(200, json={"ok": True})

    settings = MagicMock(
        telegram_bot_token="token",
        telegram_proxy_url_effective=None,
    )
    markup = MagicMock()
    markup.model_dump.return_value = {"inline_keyboard": []}

    with (
        patch("astra.workers.telegram_send.httpx.AsyncClient", return_value=_Client()),
        patch(
            "astra.workers.telegram_send._resolve_reply_markup",
            return_value={"keyboard": []},
        ),
    ):
        await send_telegram_html(42, "блок\n\n" * 2000, settings)

    assert len(sent) > 1
    assert all(len(payload["text"]) <= TELEGRAM_MESSAGE_LIMIT for payload in sent)
    assert all(payload["parse_mode"] == "HTML" for payload in sent)
    # клавиатура только под последней частью
    assert "reply_markup" not in sent[0]
    assert "reply_markup" in sent[-1]


@pytest.mark.anyio
async def test_short_answer_still_goes_as_one_message() -> None:
    from astra.workers.telegram_send import send_telegram_html

    sent: list[dict] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url: str, json: dict):  # noqa: A002
            sent.append(json)
            return httpx.Response(200, json={"ok": True})

    settings = MagicMock(telegram_bot_token="token", telegram_proxy_url_effective=None)

    with (
        patch("astra.workers.telegram_send.httpx.AsyncClient", return_value=_Client()),
        patch("astra.workers.telegram_send._resolve_reply_markup", return_value=None),
    ):
        await send_telegram_html(42, "короткий ответ", settings)

    assert len(sent) == 1
    assert sent[0]["text"] == "короткий ответ"
