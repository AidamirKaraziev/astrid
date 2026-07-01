from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from astra.telegram.button_texts import (
    BTN_ASK_STARS,
    BTN_BACK_MENU,
    BTN_COMPATIBILITY,
    BTN_GENDER_FEMALE,
    BTN_GENDER_MALE,
    BTN_INVITE,
    BTN_MONTH_FORECAST,
    BTN_NATAL,
    BTN_PREDICTION_TODAY,
    BTN_PROFILE,
    BTN_TAROT,
    BTN_TAROT_DECISION,
    BTN_TAROT_RELATIONS,
    BTN_TAROT_THREE,
    CB_PRODUCT_ASK_STARS,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PREDICTION_TODAY)],
            [
                KeyboardButton(text=BTN_COMPATIBILITY),
                KeyboardButton(text=BTN_NATAL),
            ],
            [
                KeyboardButton(text=BTN_MONTH_FORECAST),
                KeyboardButton(text=BTN_TAROT),
            ],
            [
                KeyboardButton(text=BTN_PROFILE),
                KeyboardButton(text=BTN_INVITE),
            ],
        ],
        resize_keyboard=True,
    )


def tarot_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TAROT_THREE)],
            [KeyboardButton(text=BTN_TAROT_RELATIONS)],
            [KeyboardButton(text=BTN_TAROT_DECISION)],
            [KeyboardButton(text=BTN_BACK_MENU)],
        ],
        resize_keyboard=True,
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭ Пропустить")]],
        resize_keyboard=True,
    )


def gender_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_GENDER_MALE),
                KeyboardButton(text=BTN_GENDER_FEMALE),
            ],
        ],
        resize_keyboard=True,
    )


def share_keyboard(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Поделиться с подругой",
                    url=share_url,
                ),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home")],
        ],
    )


def profile_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Имя", callback_data="profile:name")],
            [InlineKeyboardButton(text="⚧ Пол", callback_data="profile:gender")],
            [InlineKeyboardButton(text="📅 Дата рождения", callback_data="profile:date")],
            [InlineKeyboardButton(text="🕐 Время рождения", callback_data="profile:time")],
            [InlineKeyboardButton(text="📍 Место рождения", callback_data="profile:place")],
            [
                InlineKeyboardButton(
                    text="🌍 Город для уведомлений",
                    callback_data="profile:notification_city",
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:home")],
        ],
    )


def profile_gender_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_GENDER_MALE, callback_data="profile:gender:male"),
                InlineKeyboardButton(text=BTN_GENDER_FEMALE, callback_data="profile:gender:female"),
            ],
        ],
    )


def prediction_followup_keyboard() -> InlineKeyboardMarkup:
    """CTA под ежедневным предсказанием."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_ASK_STARS,
                    callback_data=CB_PRODUCT_ASK_STARS,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        ],
    )


def help_keyboard(support_username: str) -> InlineKeyboardMarkup:
    username = support_username.strip().lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💌 Написать Astrid",
                    url=f"https://t.me/{username}",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        ],
    )
