"""Тексты Reply-кнопок Telegram-бота — единый источник правды."""

BTN_PREDICTION_TODAY = "🔮 Предсказание на сегодня"
BTN_PROFILE = "✨ Обо мне"
BTN_INVITE = "🎁 Пригласить друга"
BTN_BACK_MENU = "🔙 В меню"

BTN_COMPATIBILITY = "💕 Совместимость"
BTN_ASK_STARS = "🌟 Спросить звёзды"
BTN_NATAL = "🌌 Разбор натала"
BTN_MONTH_FORECAST = "📅 Прогноз на месяц"
BTN_TAROT = "🔮 Карты Таро"

BTN_TAROT_THREE = "🃏 Три карты"
BTN_TAROT_RELATIONS = "💕 На отношения"
BTN_TAROT_DECISION = "⚖️ На решение"

BTN_GENDER_MALE = "Мужчина"
BTN_GENDER_FEMALE = "Женщина"
GENDER_REPLY_BUTTONS = frozenset({BTN_GENDER_MALE, BTN_GENDER_FEMALE})

PAID_PRODUCT_BUTTONS = (
    BTN_COMPATIBILITY,
    BTN_NATAL,
    BTN_MONTH_FORECAST,
    BTN_TAROT,
)

TAROT_PRODUCT_BUTTONS = (
    BTN_TAROT_THREE,
    BTN_TAROT_RELATIONS,
    BTN_TAROT_DECISION,
)

COMING_SOON_TEXT = "Скоро появится, выбери что-то другое."

CB_PRODUCT_ASK_STARS = "product:ask_stars"
CB_PROFILE_REPORTS = "profile:reports"
CB_COMPAT_CONTEXT_PREFIX = "compatibility:context:"
CB_COMPAT_MODE_PREFIX = "compatibility:mode:"
CB_COMPAT_CONFIRM = "compatibility:confirm:yes"
CB_COMPAT_CANCEL = "compatibility:cancel"
CB_COMPAT_REPORT_PREFIX = "compatibility:report:"
CB_COMPAT_REPORT_PDF_PREFIX = "compat:pdf:"
CB_COMPAT_REPORTS_LIST = "compat:reports:list"
CB_COMPAT_DELETE_PREFIX = "compat:del:"
CB_COMPAT_DELETE_CONFIRM_PREFIX = "compat:del:yes:"
CB_COMPAT_DELETE_CANCEL_PREFIX = "compat:del:no:"
