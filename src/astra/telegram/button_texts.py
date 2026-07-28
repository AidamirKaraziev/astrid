"""Тексты Reply-кнопок Telegram-бота — единый источник правды."""

# Ежедневный прогноз заменён картой дня (приходит рассылкой). Кнопки нет в меню,
# но у части пользователей клавиатура закэширована клиентом — текст ловим.
BTN_PREDICTION_TODAY_LEGACY = "🔮 Предсказание на сегодня"
BTN_PROFILE = "✨ Обо мне"
BTN_INVITE = "🎁 Пригласить друга"
BTN_BACK_MENU = "🔙 Назад"
# Старый текст кнопки: у части пользователей клавиатура закэширована клиентом.
BTN_BACK_MENU_LEGACY = "🔙 В меню"

# AI-чат отключён вместе с ежедневным прогнозом: кнопки в меню нет, тексты
# остались, чтобы ловить закэшированную у клиента клавиатуру.
BTN_ASK_ASTRID_LEGACY = "💬 Написать Астрид"
BTN_ASK_ASTRID_LEGACY_LATIN = "💬 Написать Astrid"
BTN_COMPATIBILITY = "💕 Совместимость"
BTN_ASK_STARS = "🌟 Спросить звёзды"
BTN_NATAL = "🌌 Разбор натала"
BTN_MONTH_FORECAST = "📅 Прогноз на месяц"
BTN_TAROT = "🔮 Карты Таро"
BTN_WHEEL = "🎡 Колесо фортуны"
BTN_HELP = "💬 Помощь"
# Раздел готовых вопросов к своей карте (не путать со «Службой заботы» — там FAQ о боте).
BTN_ASK_ASTRID = "✨ Спроси Астрид"

BTN_TAROT_THREE = "🃏 Три карты"
BTN_TAROT_RELATIONS = "💕 На отношения"
BTN_TAROT_WISH = "🌟 Загадай желание"
# Старая кнопка «На решение»: у части пользователей клавиатура закэширована клиентом.
BTN_TAROT_DECISION_LEGACY = "⚖️ На решение"
BTN_TAROT_SKIP = "⏭ Пропустить"

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
    BTN_TAROT_WISH,
)

COMING_SOON_TEXT = "Скоро появится, выбери что-то другое."

# Карта дня: кнопка под картинкой и переход к платным раскладам после прогноза
BTN_DAY_CARD_FORECAST = "🔮 Что это значит для меня"
BTN_TAROT_ASK_OWN = "🔮 Спросить карты о своём"
CB_DAY_CARD_FORECAST = "daycard:forecast"
CB_TAROT_SECTION = "tarot:section"

CB_PRODUCT_ASK_STARS = "product:ask_stars"
CB_PROFILE_REPORTS = "profile:reports"
CB_COMPAT_CONTEXT_PREFIX = "compatibility:context:"
CB_COMPAT_CONFIRM = "compatibility:confirm:yes"
CB_COMPAT_CANCEL = "compatibility:cancel"
CB_COMPAT_REPORT_PREFIX = "compatibility:report:"
CB_COMPAT_REPORT_PDF_PREFIX = "compat:pdf:"
CB_COMPAT_REPORTS_LIST = "compat:reports:list"
CB_COMPAT_DELETE_PREFIX = "compat:del:"
CB_COMPAT_DELETE_CONFIRM_PREFIX = "compat:del:yes:"
CB_COMPAT_DELETE_CANCEL_PREFIX = "compat:del:no:"

# Сохранённые натальные профили («Мои люди»)
CB_PROFILE_PEOPLE = "profile:people"
CB_PEOPLE_LIST = "people:list"
CB_PEOPLE_CARD_PREFIX = "people:card:"
CB_PEOPLE_EDIT_PREFIX = "people:edit:"  # people:edit:<field>:<id>
CB_PEOPLE_DELETE_PREFIX = "people:del:"
CB_PEOPLE_DELETE_CONFIRM_PREFIX = "people:del:yes:"
CB_PEOPLE_DELETE_CANCEL_PREFIX = "people:del:no:"
# Переиспользуемый пикер профиля в FSM-флоу (совместимость и будущие продукты)
CB_PERSON_PICK_PREFIX = "person:pick:"
# Колесо фортуны
CB_WHEEL_SPIN_FREE = "wheel:spin:free"
CB_WHEEL_SPIN_PAID = "wheel:spin:paid"
CB_WHEEL_PRIZES = "wheel:prizes"
CB_WHEEL_HOME = "wheel:home"
CB_WHEEL_ACTIVATE_PREFIX = "wheel:use:"

CB_COMPAT_NEW_PERSON = "compat:person:new"
CB_COMPAT_PEOPLE_ALL = "compat:person:all"
CB_COMPAT_SELF_FIRST = "compat:person:self"

# Служба заботы: хаб помощи, FAQ-темы и вход в релей к живому оператору
CB_SUPPORT_HUB = "support:hub"
CB_SUPPORT_FAQ_PREFIX = "support:faq:"  # + ключ темы (payment/reading/profile/notify)
CB_SUPPORT_WRITE = "support:write"
CB_SUPPORT_CLOSE = "support:close"

# «Спроси Астрид»: верхний уровень — темы. Вопросы внутри темы придут отдельно.
CB_ASK_TOPIC_PREFIX = "ask:topic:"  # + ключ темы (love/money/path/…)
CB_ASK_QUESTION_PREFIX = "ask:q:"  # + ключ вопроса (love_marriage/…)
CB_ASK_OWN = "ask:own"
# Покупка ответа: уточнение времени рождения → статус отношений → инвойс
CB_ASK_GATE_TIME = "ask:gate:time"
CB_ASK_GATE_SKIP = "ask:gate:skip"
CB_ASK_STATUS_TAKEN = "ask:status:taken"
CB_ASK_STATUS_FREE = "ask:status:free"
CB_ASK_ANSWER_ARCHIVE = "ask:archive"
CB_ASK_COMPAT_CROSSSELL = "ask:compat"
CB_ASK_HOME = "ask:home"
CB_ASK_CLOSE = "ask:close"

SUPPORT_FAQ_PAYMENT = "payment"
SUPPORT_FAQ_READING = "reading"
SUPPORT_FAQ_PROFILE = "profile"
SUPPORT_FAQ_NOTIFY = "notify"
