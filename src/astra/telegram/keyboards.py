import re

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from astra.users.gender import Gender
from astra.telegram.button_texts import (
    BTN_ASK_ASTRID,
    BTN_ASK_STARS,
    BTN_BACK_MENU,
    BTN_COMPATIBILITY,
    BTN_DAY_CARD_FORECAST,
    BTN_GENDER_FEMALE,
    BTN_GENDER_MALE,
    BTN_HELP,
    BTN_INVITE,
    BTN_MONTH_FORECAST,
    BTN_NATAL,
    BTN_NATAL_FULL_REPORT,
    BTN_PROFILE,
    BTN_PROFILE_EDIT,
    BTN_TAROT_ASK_OWN,
    BTN_TAROT,
    BTN_TAROT_RELATIONS,
    BTN_TAROT_THREE,
    BTN_TAROT_SKIP,
    BTN_TAROT_WISH,
    BTN_TIME_UNKNOWN,
    BTN_WHEEL,
    CB_COMPAT_CANCEL,
    CB_COMPAT_CONFIRM,
    CB_COMPAT_CONTEXT_PREFIX,
    CB_COMPAT_REPORT_PREFIX,
    CB_COMPAT_REPORT_PDF_PREFIX,
    CB_COMPAT_REPORTS_LIST,
    CB_COMPAT_DELETE_PREFIX,
    CB_COMPAT_DELETE_CONFIRM_PREFIX,
    CB_ASK_CLOSE,
    CB_ASK_HOME,
    CB_ASK_OWN,
    CB_ASK_QUESTION_PREFIX,
    CB_ASK_TOPIC_PREFIX,
    CB_COMPAT_DELETE_CANCEL_PREFIX,
    CB_DAY_CARD_FORECAST,
    CB_INVITE_GIFT,
    CB_INVITE_GIFT_PICK_PREFIX,
    CB_INVITE_HUB,
    CB_INVITE_LINK,
    CB_PRODUCT_ASK_STARS,
    CB_PROFILE_BACK,
    CB_PROFILE_EDIT,
    CB_PROFILE_NATAL,
    CB_PROFILE_PEOPLE,
    CB_PROFILE_REPORTS,
    CB_PROFILE_TIME_UNKNOWN,
    CB_SUPPORT_CLOSE,
    CB_SUPPORT_FAQ_PREFIX,
    CB_SUPPORT_HUB,
    CB_SUPPORT_WRITE,
    CB_TAROT_CLOSE,
    CB_TAROT_QUESTION_SKIP,
    CB_TAROT_SECTION,
    CB_TAROT_SPREAD_PREFIX,
)
from astra.tarot.spreads import SpreadType


def day_card_keyboard() -> InlineKeyboardMarkup:
    """Кнопка под картой дня: прогноз пишется по нажатию."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_DAY_CARD_FORECAST,
                    callback_data=CB_DAY_CARD_FORECAST,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        ],
    )


def day_forecast_followup_keyboard() -> InlineKeyboardMarkup:
    """CTA под готовым прогнозом: бесплатная карта дня ведёт к платным раскладам."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_ASK_OWN,
                    callback_data=CB_TAROT_SECTION,
                ),
            ],
        ],
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Колесо первым: единственная механика, куда возвращаются каждый день."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_WHEEL)],
            [KeyboardButton(text=BTN_ASK_ASTRID)],
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
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def tarot_spreads_keyboard() -> InlineKeyboardMarkup:
    """Экран раздела таро: выбор расклада."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_THREE,
                    callback_data=f"{CB_TAROT_SPREAD_PREFIX}{SpreadType.THREE_CARDS}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_RELATIONS,
                    callback_data=f"{CB_TAROT_SPREAD_PREFIX}{SpreadType.RELATIONSHIP}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_WISH,
                    callback_data=f"{CB_TAROT_SPREAD_PREFIX}{SpreadType.WISH}",
                ),
            ],
            [InlineKeyboardButton(text=BTN_BACK_MENU, callback_data=CB_TAROT_CLOSE)],
        ],
    )


def tarot_question_keyboard(*, question_required: bool) -> InlineKeyboardMarkup:
    """Экран вопроса к раскладу. «Пропустить» — только там, где вопрос не обязателен."""
    rows: list[list[InlineKeyboardButton]] = []
    if not question_required:
        rows.append(
            [
                InlineKeyboardButton(
                    text=BTN_TAROT_SKIP,
                    callback_data=CB_TAROT_QUESTION_SKIP,
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="🔙 К раскладам", callback_data=CB_TAROT_SECTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:home")],
        ],
    )


def profile_menu_keyboard() -> InlineKeyboardMarkup:
    """Под портретом: продолжение разбора, правка данных, архивы.

    Поля профиля уехали на отдельный экран (`profile_edit_keyboard`): девять
    кнопок-полей под портретом читались как форма, а не как рассказ о человеке.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_NATAL_FULL_REPORT,
                    callback_data=CB_PROFILE_NATAL,
                ),
            ],
            [InlineKeyboardButton(text=BTN_PROFILE_EDIT, callback_data=CB_PROFILE_EDIT)],
            [
                InlineKeyboardButton(
                    text="📚 Мои разборы",
                    callback_data=CB_PROFILE_REPORTS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Мои люди",
                    callback_data=CB_PROFILE_PEOPLE,
                ),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:home")],
        ],
    )


def profile_edit_keyboard() -> InlineKeyboardMarkup:
    """Поля профиля. «Назад» ведёт к портрету, а не в главное меню."""
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
            [InlineKeyboardButton(text="🔙 К портрету", callback_data=CB_PROFILE_BACK)],
        ],
    )


def profile_birth_time_keyboard() -> InlineKeyboardMarkup:
    """Ввод времени рождения: можно вписать текстом, а можно честно сказать «не знаю»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BTN_TIME_UNKNOWN,
                    callback_data=CB_PROFILE_TIME_UNKNOWN,
                ),
            ],
        ],
    )


def compatibility_context_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♥️ Любовь", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}love")],
            [InlineKeyboardButton(text="💼 Работа", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}work")],
            [InlineKeyboardButton(text="🤝 Дружба", callback_data=f"{CB_COMPAT_CONTEXT_PREFIX}friendship")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:home")],
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
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile:back")])
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
                    text="🔙 Назад",
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


def support_hub_keyboard(can_write: bool) -> InlineKeyboardMarkup:
    """Хаб помощи: темы FAQ + вход к живому оператору."""
    from astra.telegram.support_text import FAQ_BUTTONS

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"{CB_SUPPORT_FAQ_PREFIX}{key}")]
        for key, label in FAQ_BUTTONS
    ]
    if can_write:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✍️ Написать в Службу заботы",
                    callback_data=CB_SUPPORT_WRITE,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="✖️ Закрыть", callback_data=CB_SUPPORT_CLOSE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_faq_keyboard(can_write: bool) -> InlineKeyboardMarkup:
    """Под ответом FAQ: написать человеку (если можно) + назад к темам."""
    rows: list[list[InlineKeyboardButton]] = []
    if can_write:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✍️ Это не помогло — написать человеку",
                    callback_data=CB_SUPPORT_WRITE,
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        )
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=CB_SUPPORT_HUB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_writing_keyboard() -> ReplyKeyboardMarkup:
    """Режим написания обращения: только выход, текст — обычным сообщением."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BACK_MENU)]],
        resize_keyboard=True,
    )


# Вопрос или тема ещё не открыты: растущая луна вместо замка — «скоро будет»,
# а не «купи доступ». Готовое всегда идёт первым.
SOON_MARK = "🌒"


# Свой значок темы у неоткрытой кнопки заменяем, а не дополняем: один эмодзи
# на кнопку — правило стиля бота.
_LEADING_EMOJI = re.compile(r"^\W+\s*")


def _soon(label: str) -> str:
    return f"{SOON_MARK} {_LEADING_EMOJI.sub('', label)}"


def _topic_is_ready(topic_key: str) -> bool:
    from astra.ask.products import is_ready
    from astra.telegram import ask_text as A

    return any(is_ready(q.key) for q in A.ASK_QUESTIONS.get(topic_key, ()))


def ask_astrid_keyboard() -> InlineKeyboardMarkup:
    """Верхний уровень «Спроси Астрид»: темы, свой вопрос, закрыть."""
    from astra.telegram import ask_text as A

    topics = sorted(A.ASK_TOPICS, key=lambda item: not _topic_is_ready(item[0]))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=label if _topic_is_ready(key) else _soon(label),
                callback_data=f"{CB_ASK_TOPIC_PREFIX}{key}",
            ),
        ]
        for key, label in topics
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=_soon(A.BTN_ASK_OWN_QUESTION),
                callback_data=CB_ASK_OWN,
            ),
        ],
    )
    rows.append([InlineKeyboardButton(text=A.BTN_ASK_CLOSE, callback_data=CB_ASK_CLOSE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ask_questions_keyboard(topic_key: str, gender: Gender | None) -> InlineKeyboardMarkup:
    """Вопросы темы: подписи с подставленным родом, внизу свой вопрос и назад."""
    from astra.telegram import ask_text as A

    from astra.ask.products import is_ready

    questions = sorted(A.ASK_QUESTIONS.get(topic_key, ()), key=lambda q: not is_ready(q.key))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=(
                    A.render_question(question.label, gender)
                    if is_ready(question.key)
                    else _soon(A.render_question(question.label, gender))
                ),
                callback_data=f"{CB_ASK_QUESTION_PREFIX}{question.key}",
            ),
        ]
        for question in questions
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=_soon(A.BTN_ASK_OWN_QUESTION),
                callback_data=CB_ASK_OWN,
            ),
        ],
    )
    rows.append([InlineKeyboardButton(text=A.BTN_ASK_TOPICS_BACK, callback_data=CB_ASK_HOME)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ask_back_keyboard(callback_data: str = CB_ASK_HOME) -> InlineKeyboardMarkup:
    """Только возврат: к темам или к вопросам темы."""
    from astra.telegram import ask_text as A

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=A.BTN_ASK_TOPICS_BACK, callback_data=callback_data)],
        ],
    )


def support_contextual_keyboard() -> InlineKeyboardMarkup:
    """Ненавязчивая подсказка «Нужна помощь?» в точках сбоя (оплата и т.п.)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Нужна помощь?", callback_data=CB_SUPPORT_HUB)],
        ],
    )


def invite_hub_keyboard() -> InlineKeyboardMarkup:
    """Раздел приглашений: подарить, позвать, закрыть."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Подарить разбор", callback_data=CB_INVITE_GIFT)],
            [InlineKeyboardButton(text="🔗 Позвать по ссылке", callback_data=CB_INVITE_LINK)],
            [InlineKeyboardButton(text=BTN_BACK_MENU, callback_data="menu:home")],
        ],
    )


def gift_products_keyboard(products) -> InlineKeyboardMarkup:
    """Что подарить. Список приходит из каталога, а не зашит в клавиатуру."""
    rows = [
        [
            InlineKeyboardButton(
                text=product.label,
                callback_data=f"{CB_INVITE_GIFT_PICK_PREFIX}{product.code}",
            ),
        ]
        for product in products
    ]
    rows.append([InlineKeyboardButton(text=BTN_BACK_MENU, callback_data=CB_INVITE_HUB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invite_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BTN_BACK_MENU, callback_data=CB_INVITE_HUB)],
        ],
    )
