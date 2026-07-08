"""Клавиатуры сохранённых натальных профилей: пикер для флоу и экран «Мои люди»."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.compatibility.models import NatalProfile
from astra.telegram.button_texts import (
    BTN_GENDER_FEMALE,
    BTN_GENDER_MALE,
    CB_PEOPLE_CARD_PREFIX,
    CB_PEOPLE_DELETE_CANCEL_PREFIX,
    CB_PEOPLE_DELETE_CONFIRM_PREFIX,
    CB_PEOPLE_DELETE_PREFIX,
    CB_PEOPLE_EDIT_PREFIX,
    CB_PEOPLE_LIST,
    CB_PERSON_PICK_PREFIX,
)


def _profile_button_label(profile: NatalProfile) -> str:
    return f"{profile.label} · {profile.birth_date.strftime('%d.%m.%Y')}"[:60]


def person_pick_keyboard(profiles: list[NatalProfile]) -> InlineKeyboardMarkup:
    """Пикер сохранённого человека внутри FSM-флоу (совместимость и будущие продукты)."""
    rows = [
        [
            InlineKeyboardButton(
                text=_profile_button_label(profile),
                callback_data=f"{CB_PERSON_PICK_PREFIX}{profile.id}",
            ),
        ]
        for profile in profiles
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def people_list_keyboard(profiles: list[NatalProfile]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_profile_button_label(profile),
                callback_data=f"{CB_PEOPLE_CARD_PREFIX}{profile.id}",
            ),
        ]
        for profile in profiles
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="profile:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def people_card_keyboard(profile_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Имя",
                    callback_data=f"{CB_PEOPLE_EDIT_PREFIX}name:{profile_id}",
                ),
                InlineKeyboardButton(
                    text="⚧ Пол",
                    callback_data=f"{CB_PEOPLE_EDIT_PREFIX}gender:{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📅 Дата",
                    callback_data=f"{CB_PEOPLE_EDIT_PREFIX}date:{profile_id}",
                ),
                InlineKeyboardButton(
                    text="🕐 Время",
                    callback_data=f"{CB_PEOPLE_EDIT_PREFIX}time:{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📍 Место рождения",
                    callback_data=f"{CB_PEOPLE_EDIT_PREFIX}place:{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"{CB_PEOPLE_DELETE_PREFIX}{profile_id}",
                ),
            ],
            [InlineKeyboardButton(text="◀️ К списку", callback_data=CB_PEOPLE_LIST)],
        ],
    )


CB_PEOPLE_GENDER_PREFIX = "people:gender:"  # people:gender:<male|female>:<id>


def people_gender_keyboard(profile_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_GENDER_MALE,
                    callback_data=f"{CB_PEOPLE_GENDER_PREFIX}male:{profile_id}",
                ),
                InlineKeyboardButton(
                    text=BTN_GENDER_FEMALE,
                    callback_data=f"{CB_PEOPLE_GENDER_PREFIX}female:{profile_id}",
                ),
            ],
        ],
    )


def people_delete_confirm_keyboard(profile_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить",
                    callback_data=f"{CB_PEOPLE_DELETE_CONFIRM_PREFIX}{profile_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"{CB_PEOPLE_DELETE_CANCEL_PREFIX}{profile_id}",
                ),
            ],
        ],
    )
