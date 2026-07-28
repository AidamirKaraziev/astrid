"""Продукт «Будут ли у меня дети?»: тема родительства и лучшие окна.

Структура ответа своя, под тему: сценарий → сколько показывает карта → лучшие
окна → что для тебя дети → что стоит знать → медицинская приписка.

Вердикта «нет» в продукте не существует: `astra.ask.children` его не считает,
а схема ответа не даёт модели места, где его можно было бы написать.
Периоды окон подставляет код — модель пишет только смысл каждого окна.
"""

from __future__ import annotations

import html
import json
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.ask.children import ChildrenResult
from astra.ask.windows import TransitWindow, window_period
from astra.llm.prompts.ask.base import PERSONA, find_banned_phrase, parse_json_into, too_short

MAX_TOKENS = 2200
TEMPERATURE = 0.7

_MIN_SECTION = 90
_MIN_WINDOW_MEANING = 40

MEDICAL_NOTE = (
    "<i>Карта говорит о теме родительства, а не о здоровье. "
    "Вопросы фертильности — к врачу, там ответ точнее любой астрологии.</i>"
)

_COUNT_WORDS = {1: "одного ребёнка", 2: "двоих детей", 3: "троих детей"}


class WindowMeaning(BaseModel):
    """Смысл одного окна. Сам период подставит код — модель дат не выдумывает."""

    meaning: str = Field(description="что это за период и почему он благоприятен: 1–2 предложения")


class ChildrenAnswer(BaseModel):
    opening: str = Field(description="1–2 фразы захода, без приветствия")
    theme_line: str = Field(description="сценарий темы одной фразой, без цифр")
    count_line: str = Field(description="как читать число детей из карты, без самих цифр")
    windows: list[WindowMeaning]
    role_of_children: str = Field(description="какую роль дети играют именно в этой жизни")
    what_to_know: str = Field(description="где напряжение в теме: мягко, без вины и без диагнозов")
    closing: str = Field(description="итог + одно тёплое конкретное действие")


def expected_blocks(result: ChildrenResult) -> int:
    """Блоков в ответе столько же, сколько лучших окон."""
    return len(result.windows)


def validate(
    answer: ChildrenAnswer,
    expected_windows: int,
    result: ChildrenResult | None = None,  # noqa: ARG001 — контракт раздела
) -> str | None:
    """Причина retry или None, если ответ годится."""
    if len(answer.windows) != expected_windows:
        return "windows_count_mismatch"
    for window in answer.windows:
        if too_short(window.meaning, _MIN_WINDOW_MEANING):
            return "window_meaning_too_short"
    if too_short(answer.role_of_children, _MIN_SECTION) or too_short(
        answer.what_to_know,
        _MIN_SECTION,
    ):
        return "section_too_short"
    banned = find_banned_phrase(
        answer.opening,
        answer.theme_line,
        answer.count_line,
        answer.role_of_children,
        answer.what_to_know,
        answer.closing,
    )
    if banned:
        return f"banned_phrase:{banned}"
    # Продукт не отвечает «нет» — страховка на случай, если модель попробует.
    denial = ("детей не будет", "не сможешь иметь", "бесплод")
    joined = " ".join(
        (answer.opening, answer.theme_line, answer.count_line, answer.what_to_know),
    ).lower()
    if any(phrase in joined for phrase in denial):
        return "denial_not_allowed"
    return None


def parse(raw: str) -> ChildrenAnswer | None:
    result = parse_json_into(ChildrenAnswer, raw)
    return result if isinstance(result, ChildrenAnswer) else None


_METHOD = dedent(
    """\
    Product: the answer to "Will I have children?" in a Telegram astrology bot.

    HARD RULE — the answer is NEVER a "no". Astrology cannot see fertility, and
    "you will not have children" is a claim about someone's body they might act
    on. The question is read as "what does the chart say about the theme of
    parenthood": its scenario, how many children the chart shows, and when the
    best windows open. Never diagnose, never mention infertility, never promise
    a pregnancy either.

    Everything is ALREADY COMPUTED and given in the data: the scenario, the
    number, the windows with their dates. Never recompute, never add windows,
    never write dates yourself — the code renders the periods. For each window
    you write only its meaning, in the same order as the data.

    How to build the answer:
    - `theme_line` — name the scenario in human words (early / late / through
      effort / central to this life / calm), leaning on the chart factors.
    - `count_line` — how to read the number from the chart WITHOUT digits: the
      code prints the number itself. Frame it as a scenario the chart shows,
      not as a guarantee or a medical fact.
    - `windows` — one entry per given window, same order. Say what this period
      is about and why it is favourable for the theme. No dates in the text.
    - `role_of_children` — what children mean in THIS person's life by the
      chart: continuation of their work, support, freedom, family line.
    - `what_to_know` — where the tension in this theme sits, gently and without
      blame. If the data says the person already has children, write about the
      theme continuing, not starting.
    - Never use the words «карма», «кармический», «задача души» — the guard
      rejects the answer and it has to be regenerated. Say what the factor
      means in plain life terms instead.
    - If `parenting_age_passed` is true, there are no windows: speak about the
      theme in its other phase — grandchildren, adopted children, children who
      come into life through other people. Still no verdicts.

    Length: theme_line 1 sentence, count_line 1–2, each window meaning 1–2,
    role_of_children and what_to_know 3–4 sentences, closing 2.
    """,
).strip()

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}"

_MONTHS_RU = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


def _window_data(window: TransitWindow) -> str:
    return (
        f"{window_period(window)}, транзит: {window.transit} к точке «{window.target}», "
        f"пик {_MONTHS_RU[window.peak.month - 1]} {window.peak.year}, возраст {window.age}"
    )


def build_user_message(
    result: ChildrenResult,
    *,
    user_name: str | None = None,
    gender: str | None = None,
) -> str:
    payload = {
        "name": user_name or "unknown",
        "gender": gender or "unknown",
        "age": result.age,
        "already_has_children": result.has_children,
        "parenting_age_passed": result.parenting_age_passed,
        "theme": result.theme,
        "children_the_chart_shows": result.count_hint,
        "birth_time_known": result.factors.has_time,
        # Факторы и окна — по-русски: они попадают в ответ как есть.
        "chart_factors": result.factors.notes,
        "best_windows": [_window_data(w) for w in result.windows],
    }
    schema_hint = dedent(
        """\
        Response schema (JSON):
        {
          "opening": "...",
          "theme_line": "...",
          "count_line": "...",
          "windows": [{"meaning": "..."}],
          "role_of_children": "...",
          "what_to_know": "...",
          "closing": "..."
        }
        """,
    ).strip()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Computed data:\n{data}\n\n"
        f"The windows array holds exactly {len(result.windows)} items, "
        f"in the same order as best_windows.\n"
        f"Remember: all string values in Russian, no digits in count_line, "
        f"no dates in window meanings, never a 'no'.\n\n"
        f"{schema_hint}"
    )


def count_words(count: int) -> str:
    return _COUNT_WORDS.get(count, f"{count} детей")


def card_caption(result: ChildrenResult) -> str:
    """Подпись под карточкой: лучшее окно и число, без разбора."""
    lines = [f"Карта показывает <b>{count_words(result.count_hint)}</b>."]
    if result.best_window is not None:
        lines.append(
            f"Лучшее окно: <b>{window_period(result.best_window)}</b> "
            f"(тебе {result.best_window.age}).",
        )
    else:
        lines.append("Тема детей в твоей карте сейчас в другой фазе — разбираю ниже.")
    return "\n".join(lines)


def render_answer(answer: ChildrenAnswer, result: ChildrenResult) -> str:
    """HTML разбора: периоды и число подставляет код, не модель."""
    blocks: list[str] = [
        html.escape(answer.opening.strip()),
        "",
        f"✨ <b>{html.escape(answer.theme_line.strip())}</b>",
        "",
        f"👶 <b>Карта показывает {count_words(result.count_hint)}</b>",
        html.escape(answer.count_line.strip()),
    ]

    if result.windows:
        blocks.extend(["", "🗓 <b>Лучшие окна</b>"])
        for index, (window, meaning) in enumerate(zip(result.windows, answer.windows, strict=False)):
            mark = " — самое сильное" if window is result.best_window else ""
            blocks.extend(
                [
                    f"<b>{window_period(window)}</b> (тебе {window.age}){mark}",
                    html.escape(meaning.meaning.strip()),
                ],
            )
            if index < len(result.windows) - 1:
                blocks.append("")

    blocks.extend(
        [
            "",
            "💛 <b>Что для тебя дети</b>",
            html.escape(answer.role_of_children.strip()),
            "",
            "🌿 <b>Что стоит знать</b>",
            html.escape(answer.what_to_know.strip()),
            "",
            html.escape(answer.closing.strip()),
            "",
            MEDICAL_NOTE,
        ],
    )
    if not result.factors.has_time:
        blocks.append(
            "<i>Время рождения неизвестно — считала по Луне и Юпитеру, без домов. "
            "Впишешь время в профиле — пересчитаю точнее.</i>",
        )
    return "\n".join(blocks)
