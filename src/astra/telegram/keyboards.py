from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔮 Предсказание на сегодня")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎁 Пригласить друга")],
        ],
        resize_keyboard=True,
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭ Пропустить")]],
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
