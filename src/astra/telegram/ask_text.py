"""Тексты раздела «Спроси Астрид»: темы верхнего уровня.

Раздел отвечает на конкретный вопрос по натальной карте — в отличие от
«Службы заботы» (там FAQ о самом боте). Сейчас реализован только верхний
уровень: список тем. Вопросы внутри темы и оплата придут отдельно.

Названия тем — человеческие формулировки, а не рубрики: «Деньги и работа»,
а не «Финансы и карьера». Тема должна обещать ответ, а не категорию.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from astra.users.gender import GENDER_FEMALE, GENDER_MALE, Gender

ASK_TOPIC_LOVE = "love"
ASK_TOPIC_MONEY = "money"
ASK_TOPIC_PATH = "path"
ASK_TOPIC_SELF = "self"
ASK_TOPIC_BODY = "body"
ASK_TOPIC_MOVE = "move"
ASK_TOPIC_FAMILY = "family"
ASK_TOPIC_NOW = "now"

# Порядок кнопок = порядок спроса: любовь и деньги сверху, «мой период» замыкает.
ASK_TOPICS: tuple[tuple[str, str], ...] = (
    (ASK_TOPIC_LOVE, "❤️ Любовь, отношения, брак"),
    (ASK_TOPIC_MONEY, "💼 Деньги и работа"),
    (ASK_TOPIC_PATH, "🧭 Путь и предназначение"),
    (ASK_TOPIC_SELF, "🧬 Характер и опоры"),
    (ASK_TOPIC_BODY, "🫀 Тело и силы"),
    (ASK_TOPIC_MOVE, "✈️ Переезд и другая страна"),
    (ASK_TOPIC_FAMILY, "👪 Семья и род"),
    (ASK_TOPIC_NOW, "🌪 Мой период"),
)

ASK_TOPIC_LABELS: dict[str, str] = dict(ASK_TOPICS)

BTN_ASK_OWN_QUESTION = "✍️ У меня свой вопрос"
BTN_ASK_TOPICS_BACK = "🔙 Назад"
BTN_ASK_CLOSE = "✖️ Закрыть"

ASK_HUB_TEXT = (
    "✨ <b>Спроси Астрид</b>\n\n"
    "Смотрю твою карту и то, что происходит с ней прямо сейчас — "
    "и отвечаю на конкретный вопрос, а не общими словами.\n\n"
    "Выбери тему:"
)

ASK_TOPIC_INTRO_TEXT = "{label}\n\nВыбери вопрос — или просто напиши свой:"

# Темы без своих вопросов: говорим честно, без «скоро будет всё».
ASK_TOPIC_SOON_TEXT = (
    "{label}\n\n"
    "Вопросы по этой теме уже готовлю — открою здесь совсем скоро ✨"
)

ASK_QUESTION_SOON_TEXT = (
    "{question}\n\n"
    "Ответ по твоей карте уже собираю — открою здесь совсем скоро ✨"
)

# ─────────── «Сколько судьбоносных партнёров?»: экраны покупки ───────────

ASK_NEED_PROFILE_TEXT = (
    "Чтобы ответить по твоей карте, мне нужна дата и место рождения. "
    "Загляни в «✨ Обо мне» — там пара шагов, и я всё посчитаю."
)

# Текст общий для всех вопросов: дома нужны каждому продукту раздела.
ASK_GATE_TIME_TEXT = (
    "🕐 <b>Время рождения</b>\n\n"
    "Со временем рождения я вижу дома карты — именно они отвечают на такие "
    "вопросы точнее всего.\n\n"
    "Без времени тоже отвечу — по планетам и их аспектам, — но без домов "
    "и без точных сроков."
)

ASK_ANSWER_COMING_TEXT = "Собираю разбор — он придёт следующим сообщением 💜"

ASK_ARCHIVE_TEXT = (
    "📖 <b>Твой ответ уже готов</b>\n\n"
    "Карта одна — значит и ответ один. Он сохранён и открывается бесплатно, "
    "сколько угодно раз.\n\n"
    "<i>Можно заказать разбор заново: расчёт по карте тот же — числа и выводы "
    "не изменятся, — но Астрид напишет его другими словами.</i>"
)

ASK_COMPAT_CROSSSELL_TEXT = (
    "Про конкретного человека я отвечу по вашим двум картам — это раздел "
    "«💕 Совместимость» в меню. Там нужна его дата рождения."
)

ASK_OWN_SOON_TEXT = (
    "✍️ <b>Свой вопрос</b>\n\n"
    "Скоро можно будет спросить своими словами — и я отвечу по твоей карте. "
    "Ещё немного 💜"
)


class AskQuestion(NamedTuple):
    """Вопрос внутри темы: ключ для callback + подпись кнопки.

    В подписи допустима форма рода `{женская|мужская|нейтральная}` — её
    раскрывает `render_question()` по полу из профиля. Нейтральная форма может
    быть пустой: лишние пробелы схлопываются.
    """

    key: str
    label: str


_GENDER_FORM_RE = re.compile(r"\{([^{}]*)\}")


def render_question(label: str, gender: Gender | None) -> str:
    """Подставить род в подпись вопроса: пол не задан — нейтральная форма."""

    def _pick(match: re.Match[str]) -> str:
        forms = match.group(1).split("|")
        if gender == GENDER_FEMALE:
            return forms[0]
        if gender == GENDER_MALE:
            return forms[1] if len(forms) > 1 else forms[0]
        return forms[2] if len(forms) > 2 else forms[0]

    return " ".join(_GENDER_FORM_RE.sub(_pick, label).split())


# Вопросы темы. Формулировки утверждены отдельно: коротко, со знаком вопроса,
# от первого лица. Остальные темы наполняются следующими заходами.
ASK_QUESTIONS: dict[str, tuple[AskQuestion, ...]] = {
    ASK_TOPIC_LOVE: (
        AskQuestion("love_fated_count", "Сколько судьбоносных партнёров?"),
        AskQuestion("love_kids", "Будут ли у меня дети?"),
        AskQuestion("love_kids_bond", "Какими будут отношения с детьми?"),
        AskQuestion("love_partner_traits", "Черты моего судьбоносного партнёра?"),
        AskQuestion("love_pain_loop", "Почему я снова и снова обжигаюсь?"),
        AskQuestion("love_where_meet", "Где меня ждёт судьбоносная встреча?"),
        AskQuestion("love_already_near", "Мой человек уже есть в моей жизни?"),
        AskQuestion("love_magnetism", "Как включить свой магнетизм?"),
        AskQuestion("love_solitude_end", "Когда закончится моё одиночество?"),
        AskQuestion("love_marriage", "Ждёт ли меня брак?"),
        AskQuestion("love_why_single", "Почему я до сих пор {одна|один|не в паре}?"),
        AskQuestion("love_self_sabotage", "Как я {сама|сам|} рушу близость?"),
    ),
}

ASK_QUESTION_BY_KEY: dict[str, AskQuestion] = {
    question.key: question for questions in ASK_QUESTIONS.values() for question in questions
}

# Обратная связь вопрос → тема: нужна кнопке «Назад» с экрана вопроса.
ASK_QUESTION_TOPIC: dict[str, str] = {
    question.key: topic for topic, questions in ASK_QUESTIONS.items() for question in questions
}
