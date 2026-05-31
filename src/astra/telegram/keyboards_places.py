from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from astra.places.models import Place


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
