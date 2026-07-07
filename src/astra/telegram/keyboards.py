from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from astra.compatibility.enums import PAIR_MODE_LABELS, PairMode
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
    CB_COMPAT_CANCEL,
    CB_COMPAT_CONFIRM,
    CB_COMPAT_CONTEXT_PREFIX,
    CB_COMPAT_MODE_PREFIX,
    CB_COMPAT_REPORT_PREFIX,
    CB_COMPAT_REPORT_PDF_PREFIX,
    CB_COMPAT_REPORTS_LIST,
    CB_COMPAT_DELETE_PREFIX,
    CB_COMPAT_DELETE_CONFIRM_PREFIX,
    CB_COMPAT_DELETE_CANCEL_PREFIX,
    CB_PRODUCT_ASK_STARS,
    CB_PROFILE_REPORTS,
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
            [
                InlineKeyboardButton(
                    text="📚 Мои разборы",
                    callback_data=CB_PROFILE_REPORTS,
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:home")],
        ],
    )


def compatibility_context_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💑 Отношения", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}love")],
            [InlineKeyboardButton(text="💼 Работа", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}work")],
            [InlineKeyboardButton(text="🤝 Дружба", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}friendship")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:home")],
        ],
    )


def compatibility_pair_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💞 " + PAIR_MODE_LABELS[PairMode.ME_PARTNER],
                callback_data=f"{CB_COMPAT_MODE_PREFIX}me_partner",
            )],
            [InlineKeyboardButton(
                text="🫂 " + PAIR_MODE_LABELS[PairMode.TWO_PEOPLE],
                callback_data=f"{CB_COMPAT_MODE_PREFIX}two_people",
            )],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}back")],
        ],
    )


def compatibility_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать разбор", callback_data=CB_COMPAT_CONFIRM)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=CB_COMPAT_CANCEL)],
        ],
    )


def compatibility_reports_keyboard(report_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label[:60], callback_data=f"{CB_COMPAT_REPORT_PREFIX}{report_id}")]
        for label, report_id in report_buttons
    ]
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="profile:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def compatibility_report_card_keyboard(report_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Получить PDF",
                    callback_data=f"{CB_COMPAT_REPORT_PDF_PREFIX}{report_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"{CB_COMPAT_DELETE_PREFIX}{report_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ К списку",
                    callback_data=CB_COMPAT_REPORTS_LIST,
                ),
            ],
        ],
    )


def compatibility_delete_confirm_keyboard(report_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить",
                    callback_data=f"{CB_COMPAT_DELETE_CONFIRM_PREFIX}{report_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"{CB_COMPAT_DELETE_CANCEL_PREFIX}{report_id}",
                ),
            ],
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


CB_TAROT_DAILY = "tarot:daily"
BTN_TAROT_DAILY = "🎴 Спросить карты"


def prediction_followup_keyboard() -> InlineKeyboardMarkup:
    """CTA под ежедневным предсказанием: карты отвечают на конфликт дня."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_DAILY,
                    callback_data=CB_TAROT_DAILY,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BTN_ASK_STARS,
                    callback_data=CB_PRODUCT_ASK_STARS,
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
