from uuid import UUID

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from astra.places.models import Place

BTN_SEND_LOCATION = "📍 Отправить мою геолокацию"
BTN_SEND_LOCATION_LEGACY = (
    "📍 Отправить мою геолокацию",
    "📍 Отправить геолокацию",
    "💻 Геолокация (компьютер)",
)
BTN_TYPE_PLACE_NAME = "⌨️ Ввести название вручную"

LOCATION_BUTTON_TEXTS = (BTN_SEND_LOCATION, *BTN_SEND_LOCATION_LEGACY)
PLACE_KEYBOARD_BUTTON_TEXTS = (*LOCATION_BUTTON_TEXTS, BTN_TYPE_PLACE_NAME)


def places_pick_keyboard(places: list[Place]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=p.display_name[:64], callback_data=f"place:pick:{p.id}")]
        for p in places
    ]
    rows.append([InlineKeyboardButton(text="🔍 Ввести другой запрос", callback_data="place:retry")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def place_confirm_keyboard(place_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, верно", callback_data=f"place:confirm:{place_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="place:retry"),
            ],
        ],
    )


def place_step_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SEND_LOCATION, request_location=True)],
            [KeyboardButton(text=BTN_TYPE_PLACE_NAME)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
