"""Раздел «Спроси Астрид»: верхний уровень — темы вопросов."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from astra.telegram import ask_text as A
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_HELP,
    CB_ASK_CLOSE,
    CB_ASK_HOME,
    CB_ASK_OWN,
    CB_ASK_QUESTION_PREFIX,
    CB_ASK_TOPIC_PREFIX,
)
from astra.telegram.handlers import ask_astrid
from astra.telegram.keyboard_policy import MAIN_MENU_BUTTONS
from astra.telegram.keyboards import ask_astrid_keyboard, ask_questions_keyboard, main_menu_keyboard
from astra.users.gender import GENDER_FEMALE, GENDER_MALE


async def _fsm() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=3))


def _callback(data: str | None = None) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.data = data
    callback.from_user = SimpleNamespace(id=777)
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()
    return callback


def _user(gender: str | None) -> SimpleNamespace:
    return SimpleNamespace(profile=SimpleNamespace(gender=gender))


def _with_user(gender: str | None = None):
    """Подменяем загрузку пользователя: род в подписях берётся из профиля."""
    return patch.object(
        ask_astrid.users_crud,
        "get_user_by_telegram_id",
        AsyncMock(return_value=_user(gender)),
    )


# ─────────────────────────── клавиатуры ───────────────────────────


def test_main_menu_has_ask_astrid_under_wheel() -> None:
    rows = [[btn.text for btn in row] for row in main_menu_keyboard().keyboard]
    assert rows[1] == [BTN_ASK_ASTRID]
    assert BTN_ASK_ASTRID in MAIN_MENU_BUTTONS


def test_ask_astrid_name_does_not_collide_with_support() -> None:
    # «Помощь» — про бота, «Спроси Астрид» — про карту: разные разделы.
    assert BTN_ASK_ASTRID != BTN_HELP


def test_hub_keyboard_lists_all_topics_then_own_question_and_close() -> None:
    rows = ask_astrid_keyboard().inline_keyboard
    data = [btn.callback_data for row in rows for btn in row]

    assert sorted(data[: len(A.ASK_TOPICS)]) == sorted(
        f"{CB_ASK_TOPIC_PREFIX}{key}" for key, _ in A.ASK_TOPICS
    )
    assert data[-2:] == [CB_ASK_OWN, CB_ASK_CLOSE]
    assert len(A.ASK_TOPICS) == 8


def test_open_topics_go_first_and_closed_ones_are_marked() -> None:
    """Неоткрытые темы помечены растущей луной, готовые — сверху."""
    from astra.telegram.keyboards import SOON_MARK

    labels = [btn.text for row in ask_astrid_keyboard().inline_keyboard for btn in row]
    topics = labels[: len(A.ASK_TOPICS)]

    assert topics[0] == A.ASK_TOPIC_LABELS[A.ASK_TOPIC_LOVE]  # в «Любви» есть готовые
    assert all(label.startswith(SOON_MARK) for label in topics[1:])
    # Значок темы заменён, а не дополнен: один эмодзи на кнопку.
    assert "🌒 💼" not in " ".join(topics)


def test_ready_questions_go_first_and_the_rest_are_marked() -> None:
    from astra.ask.products import is_ready
    from astra.telegram.keyboards import SOON_MARK

    rows = ask_questions_keyboard(A.ASK_TOPIC_LOVE, GENDER_FEMALE).inline_keyboard
    buttons = [btn for row in rows for btn in row]
    questions = [
        btn for btn in buttons if (btn.callback_data or "").startswith(CB_ASK_QUESTION_PREFIX)
    ]
    keys = [(btn.callback_data or "").removeprefix(CB_ASK_QUESTION_PREFIX) for btn in questions]

    ready_flags = [is_ready(key) for key in keys]
    assert ready_flags == sorted(ready_flags, reverse=True), "готовые вопросы должны идти первыми"
    for btn, key in zip(questions, keys, strict=True):
        assert btn.text.startswith(SOON_MARK) is not is_ready(key)


def test_every_topic_is_one_full_width_row() -> None:
    rows = ask_astrid_keyboard().inline_keyboard
    assert all(len(row) == 1 for row in rows)


# ─────────────────────────── вход в раздел ───────────────────────────


@pytest.mark.asyncio
async def test_menu_button_opens_hub_and_clears_state() -> None:
    state = await _fsm()
    await state.set_data({"stale": True})
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()

    await ask_astrid.ask_astrid_button(message, state)

    assert await state.get_state() is None
    assert message.answer.await_args.args[0] == A.ASK_HUB_TEXT


# ─────────────────────────── темы ───────────────────────────


@pytest.mark.asyncio
async def test_topic_without_questions_says_they_are_coming() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_NOW}")

    with _with_user():
        await ask_astrid.cb_ask_topic(callback, MagicMock())

    text = callback.message.edit_text.await_args.args[0]
    assert A.ASK_TOPIC_LABELS[A.ASK_TOPIC_NOW] in text
    assert "скоро" in text.lower()
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == CB_ASK_HOME


@pytest.mark.asyncio
async def test_unknown_topic_is_ignored() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}unknown")

    with _with_user():
        await ask_astrid.cb_ask_topic(callback, MagicMock())

    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_love_topic_shows_its_questions() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_LOVE}")

    with _with_user(GENDER_FEMALE):
        await ask_astrid.cb_ask_topic(callback, MagicMock())

    text = callback.message.edit_text.await_args.args[0]
    assert A.ASK_TOPIC_LABELS[A.ASK_TOPIC_LOVE] in text
    rows = callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
    data = [btn.callback_data for row in rows for btn in row]
    assert sorted(data[:12]) == sorted(
        f"{CB_ASK_QUESTION_PREFIX}{q.key}" for q in A.ASK_QUESTIONS[A.ASK_TOPIC_LOVE]
    )
    assert data[-2:] == [CB_ASK_OWN, CB_ASK_HOME]


@pytest.mark.asyncio
async def test_topic_falls_back_to_new_message_when_edit_fails() -> None:
    callback = _callback(f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_MONEY}")
    callback.message.edit_text = AsyncMock(side_effect=Exception("message has photo"))

    with _with_user():
        await ask_astrid.cb_ask_topic(callback, MagicMock())

    assert A.ASK_TOPIC_LABELS[A.ASK_TOPIC_MONEY] in callback.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_home_returns_to_topics() -> None:
    back = _callback(CB_ASK_HOME)

    await ask_astrid.cb_ask_home(back)

    assert back.message.edit_text.await_args.args[0] == A.ASK_HUB_TEXT


# ─────────────────────────── вопросы темы ───────────────────────────


def test_love_topic_has_twelve_questions_with_question_marks() -> None:
    questions = A.ASK_QUESTIONS[A.ASK_TOPIC_LOVE]
    assert len(questions) == 12
    assert all(q.label.endswith("?") for q in questions)
    assert len({q.key for q in questions}) == 12


def test_question_labels_fit_telegram_button() -> None:
    for question in A.ASK_QUESTION_BY_KEY.values():
        rendered = A.render_question(question.label, GENDER_FEMALE)
        assert len(rendered) <= 40, rendered


def test_gender_is_substituted_in_labels() -> None:
    single = A.ASK_QUESTION_BY_KEY["love_why_single"].label
    assert A.render_question(single, GENDER_FEMALE) == "Почему я до сих пор одна?"
    assert A.render_question(single, GENDER_MALE) == "Почему я до сих пор один?"
    assert A.render_question(single, None) == "Почему я до сих пор не в паре?"

    sabotage = A.ASK_QUESTION_BY_KEY["love_self_sabotage"].label
    assert A.render_question(sabotage, GENDER_FEMALE) == "Как я сама рушу близость?"
    assert A.render_question(sabotage, GENDER_MALE) == "Как я сам рушу близость?"
    # Пол не задан — форма выпадает целиком, лишний пробел не остаётся.
    assert A.render_question(sabotage, None) == "Как я рушу близость?"


def test_keyboard_renders_gender_of_the_user() -> None:
    labels = [
        btn.text
        for row in ask_questions_keyboard(A.ASK_TOPIC_LOVE, GENDER_MALE).inline_keyboard
        for btn in row
    ]
    # Вопрос ещё не открыт — подпись идёт с пометкой «скоро».
    assert any(label.endswith("Почему я до сих пор один?") for label in labels)


@pytest.mark.asyncio
async def test_question_says_answer_is_coming_and_returns_to_its_topic() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}love_marriage")

    with _with_user(GENDER_FEMALE):
        await ask_astrid.cb_ask_question(callback, await _fsm(), MagicMock())

    text = callback.message.edit_text.await_args.args[0]
    assert "Ждёт ли меня брак?" in text
    assert "скоро" in text.lower()
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    back = markup.inline_keyboard[0][0].callback_data
    assert back == f"{CB_ASK_TOPIC_PREFIX}{A.ASK_TOPIC_LOVE}"


@pytest.mark.asyncio
async def test_unknown_question_is_ignored() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}nope")

    with _with_user():
        await ask_astrid.cb_ask_question(callback, await _fsm(), MagicMock())

    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_question_without_profile_uses_neutral_form() -> None:
    callback = _callback(f"{CB_ASK_QUESTION_PREFIX}love_why_single")

    with patch.object(
        ask_astrid.users_crud,
        "get_user_by_telegram_id",
        AsyncMock(return_value=None),
    ):
        await ask_astrid.cb_ask_question(callback, await _fsm(), MagicMock())

    assert "Почему я до сих пор не в паре?" in callback.message.edit_text.await_args.args[0]


# ─────────────────────────── свой вопрос и закрытие ───────────────────────────


@pytest.mark.asyncio
async def test_own_question_says_it_is_coming() -> None:
    callback = _callback(CB_ASK_OWN)

    await ask_astrid.cb_ask_own(callback)

    assert callback.message.edit_text.await_args.args[0] == A.ASK_OWN_SOON_TEXT


@pytest.mark.asyncio
async def test_close_deletes_message() -> None:
    callback = _callback(CB_ASK_CLOSE)

    await ask_astrid.cb_ask_close(callback)

    callback.message.delete.assert_awaited_once()
