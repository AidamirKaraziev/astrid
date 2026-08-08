"""Политика Reply-клавиатур: зоны меню и сериализация для Bot API."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_INVITE,
    BTN_PROFILE,
    BTN_WHEEL,
    BTN_TAROT,
    PAID_PRODUCT_BUTTONS,
)
from astra.telegram.keyboards import main_menu_keyboard
from astra.telegram.states import (
    AiChatStates,
    CompatibilityStates,
    NatalStates,
    BirthDataStates,
    OnboardingStates,
    PeopleStates,
    PlaceStates,
    ProfileStates,
    SupportStates,
    TarotStates,
)

_KEYBOARD_SUPPRESSED_FSM_STATES: frozenset[str] = frozenset(
    {
        # AI-чат: держим свою «Назад»-клавиатуру, не подставляем главное меню.
        AiChatStates.chatting.state,
        OnboardingStates.welcome.state,
        OnboardingStates.gender.state,
        # Добор данных: человек посреди продукта отвечает на вопрос, и главное
        # меню под рукой уводит его из сценария одним касанием.
        BirthDataStates.date.state,
        BirthDataStates.place_query.state,
        ProfileStates.edit_birth_place_query.state,
        ProfileStates.edit_notification_place_query.state,
        CompatibilityStates.birth_place_query.state,
        CompatibilityStates.collect_name.state,
        CompatibilityStates.collect_gender.state,
        CompatibilityStates.collect_birth_date.state,
        CompatibilityStates.collect_birth_time.state,
        PeopleStates.edit_name.state,
        PeopleStates.edit_birth_date.state,
        PeopleStates.edit_birth_time.state,
        PeopleStates.edit_birth_place_query.state,
        NatalStates.new_name.state,
        NatalStates.new_gender.state,
        NatalStates.new_birth_date.state,
        NatalStates.new_birth_time.state,
        NatalStates.new_birth_place_query.state,
        # Ввод вопроса к раскладу: «Пропустить» и «К раскладам» живут на
        # inline-экране, а главное меню под рукой звало бы бросить расклад.
        TarotStates.waiting_question.state,
        # Служба заботы: пишем обращение, держим свою «Назад»-клавиатуру.
        SupportStates.writing.state,
        # Рассказ о недостающем месте: человек посреди регистрации, и главное
        # меню тут — приглашение бросить её на середине и уйти крутить колесо.
        PlaceStates.describing_missing.state,
    },
)

MAIN_MENU_BUTTONS: frozenset[str] = frozenset(
    {
        BTN_ASK_ASTRID,
        BTN_WHEEL,
        BTN_PROFILE,
        BTN_INVITE,
        *PAID_PRODUCT_BUTTONS,
    },
)

_PAID_STUB_BUTTONS: frozenset[str] = frozenset(PAID_PRODUCT_BUTTONS) - {BTN_TAROT}


class KeyboardZone(StrEnum):
    """Reply-клавиатура у бота одна — главное меню.

    Своя клавиатура была у раздела таро; раздел переехал в inline-экран, и
    зона исчезла вместе с ней. Если появится новая — добавлять сюда.
    """

    MAIN = "main"


def is_fsm_keyboard_suppressed(fsm_state: str | None) -> bool:
    return fsm_state in _KEYBOARD_SUPPRESSED_FSM_STATES


def resolve_keyboard_zone(
    *,
    incoming_text: str | None,
    fsm_state: str | None,
    skip_auto_keyboard: bool = False,
) -> KeyboardZone | None:
    """Какую Reply-клавиатуру прикрепить к ответу на это входящее сообщение."""
    if skip_auto_keyboard or is_fsm_keyboard_suppressed(fsm_state):
        return None

    # Раздел таро больше не ставит свою reply-клавиатуру: и вход в раздел, и
    # нажатия закэшированных кнопок раскладов возвращают главное меню — так
    # устаревшая клавиатура у человека сама лечится на первом же ответе бота.
    return KeyboardZone.MAIN


def reply_keyboard_for_zone(zone: KeyboardZone | None) -> ReplyKeyboardMarkup | None:
    if zone is None:
        return None
    if zone is KeyboardZone.MAIN:
        return main_menu_keyboard()
    return None


def reply_keyboard_to_api_payload(
    markup: ReplyKeyboardMarkup | ReplyKeyboardRemove,
) -> dict[str, Any]:
    """Сериализация для прямых вызовов Telegram Bot API (worker, scheduler)."""
    return markup.model_dump(mode="json", exclude_none=True)
