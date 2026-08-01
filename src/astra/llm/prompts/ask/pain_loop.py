"""Продукт «Почему я снова и снова обжигаюсь?»: разбор поверх посчитанной петли.

Петлю, точку слома и выход считает `astra.ask.pain_loop`. Модель получает их
готовыми и разворачивает в живой текст — петлю она не выбирает и не заменяет.

Самый тонкий продукт раздела, поэтому ограждения жёсткие и лежат в промпте:
никаких диагнозов, никакого обвинения человека, никакой романтизации боли и
никаких обещаний, что теперь всё наладится.

Границы продукта две:

- **Откуда петля взялась — не сюда.** Детство, родители, семейная история
  принадлежат вопросу «Как я сама рушу близость?». Здесь только сам паттерн.
- **Про насилие говорим прямо**, а не намёками: если оно есть — это не петля и
  не карма. Дальше поддержка и конкретный совет. Пишет это модель, своими
  словами; кнопки под ответом остаются такие же, как у остальных разборов.

Имя, как и в «Чертах партнёра», модель не видит — его вставляет код.
"""

from __future__ import annotations

import html
import json
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.ask.pain_loop import PainLoopResult
from astra.llm.prompts.ask.base import PERSONA, find_banned_phrase, parse_json_into, too_short
from astra.users.gender import GENDER_FEMALE, GENDER_MALE

MAX_TOKENS = 2400
TEMPERATURE = 0.7

_SIGNS_EXPECTED = 3
_MIN_SCENE = 150
_MIN_SECTION = 100
_MIN_SAFETY = 120

# Род тех, кого человек выбирает: карта его не показывает, берём от обратного
# к полу человека. Пол не задан — пишем нейтрально, ничего не додумывая.
_PARTNER_GENDER: dict[str, str] = {
    GENDER_FEMALE: "мужской",
    GENDER_MALE: "женский",
}
_PARTNER_GENDER_NEUTRAL = "нейтральный"


class PainLoopAnswer(BaseModel):
    opening: str = Field(
        description="1–2 фразы захода. Это продолжение обращения к человеку: начинай со строчной буквы",
    )
    loop_scene: str = Field(description="что именно повторяется — сценой из жизни, а не диагнозом")
    signs: list[str] = Field(description="3 признака, по которым человек узнает эту петлю у себя")
    break_scene: str = Field(description="как выглядит момент, в котором всё разваливается")
    roles: str = Field(description="что в этом делает сам человек и что делают с ним — без обвинения")
    way_out_text: str = Field(description="как посчитанный выход выглядит в обычной жизни, по шагам")
    safety: str = Field(
        description=(
            "прямо и по существу: если в отношениях есть насилие — это не петля и не карма, "
            "и астрология тут не помощник. Затем поддержка и конкретный совет, что делать"
        ),
    )
    closing: str = Field(
        description="тёплый итог в 2 фразы. Продолжение обращения: начинай со строчной",
    )


def expected_blocks(result: PainLoopResult) -> int:  # noqa: ARG001 — контракт раздела
    """Признаков петли всегда три: по трём человек себя узнаёт, по семи — нет."""
    return _SIGNS_EXPECTED


def validate(
    answer: PainLoopAnswer,
    expected_signs: int,
    result: PainLoopResult | None = None,  # noqa: ARG001 — контракт раздела
) -> str | None:
    """Причина retry или None, если ответ годится."""
    if len(answer.signs) != expected_signs:
        return "signs_count_mismatch"
    if too_short(answer.loop_scene, _MIN_SCENE):
        return "loop_scene_too_short"
    if too_short(answer.break_scene, _MIN_SECTION) or too_short(answer.roles, _MIN_SECTION):
        return "section_too_short"
    if too_short(answer.way_out_text, _MIN_SECTION):
        return "way_out_too_short"
    # Блок про безопасность обязателен: без него продукт остаётся без выхода.
    if too_short(answer.safety, _MIN_SAFETY):
        return "safety_too_short"
    banned = find_banned_phrase(
        answer.opening,
        answer.loop_scene,
        answer.break_scene,
        answer.roles,
        answer.way_out_text,
        answer.safety,
        answer.closing,
        *answer.signs,
    )
    if banned:
        return f"banned_phrase:{banned}"
    return _diagnosis_used(answer)


# Слова психиатрии и поп-психологии: продукт не ставит диагнозов.
_DIAGNOSIS_WORDS: tuple[str, ...] = (
    "созависим",
    "нарцисс",
    "абьюз",
    "токсич",
    "психопат",
    "птср",
    "невроз",
    "расстройств",
    "диагноз",
)


def _diagnosis_used(answer: PainLoopAnswer) -> str | None:
    """Диагноз в ответе — повод переписать: это не психотерапия."""
    joined = " ".join(
        (
            answer.loop_scene,
            answer.break_scene,
            answer.roles,
            answer.way_out_text,
            answer.safety,
            answer.closing,
            *answer.signs,
        ),
    ).lower()
    word = next((w for w in _DIAGNOSIS_WORDS if w in joined), None)
    return f"diagnosis:{word}" if word else None


def parse(raw: str) -> PainLoopAnswer | None:
    result = parse_json_into(PainLoopAnswer, raw)
    return result if isinstance(result, PainLoopAnswer) else None


_METHOD = dedent(
    """\
    Product: the answer to "Why do I get burned again and again?" in a Telegram
    astrology bot. The reader keeps ending up in the same painful story with
    different people, and the chart shows which story it is.

    CRITICAL: the loop, the point where it breaks and the way out are ALREADY
    COMPUTED from the natal chart and given to you in the data. Never replace
    the loop, never rename it, never offer a second one. Your job is to make the
    reader recognise themselves in it.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. Keep the JSON keys exactly as given, in English.

    WHOSE CHART THIS IS: the data describes the READER's natal chart. Houses,
    planets and aspects belong to the reader: «твоя Венера», «твой 7 дом».

    GRAMMATICAL GENDER of the people the reader chooses: field "partner_gender".
    "мужской" — «он», "женский" — «она», "нейтральный" — never reveal a gender.

    NEVER address the reader by name and never invent one — the interface adds
    the address itself. "opening" and "closing" are continuations of that
    address, so those two — and ONLY those two — start with a lowercase letter.
    Every other field is ordinary text and starts with a capital letter.

    BOUNDARY — do NOT explain where the pattern came from. No childhood, no
    parents, no family history, no «модель любви из детства». That belongs to a
    different product. Here: what repeats, where it breaks, what to do.

    FORBIDDEN, no exceptions:
    - Diagnoses and pop-psychology labels: «созависимость», «нарцисс», «абьюзер»,
      «токсичный», «травма» as a term, «расстройство». This is not therapy.
    - Blaming the reader: never «ты сама выбираешь таких», «ты это притягиваешь»,
      «пока не полюбишь себя». The loop is described, the reader is not accused.
    - Romanticising the pain: suffering is not depth and not a sign of real love.
    - Promising the loop will disappear. It can be seen and interrupted, not cured.

    DO NOT REPEAT THE COMPUTED LINES. "break_point" and "way_out" are printed
    by the interface right above your text. Never restate them word for word —
    start from the next thought and show them in action.

    How to build the answer:
    - `loop_scene` — one recognisable scene: how it starts, what the reader
      feels, how it ends. Lean on the named chart factors and say them out loud.
    - `signs` — exactly three. Each one is checkable against real life («ты
      объясняешь друзьям, почему он не пишет»), not a virtue or a trait.
    - `break_scene` — unfold the computed break point into a scene: the moment
      it always falls apart, the same moment every time.
    - `roles` — the honest part. If "leaves_first" is true, the reader is
      usually the one who walks away first — say that plainly and without
      applause. If false, they are usually the one left — say that without pity
      and without turning them into a victim. Both are описание, not a verdict.
      Hold that role for the whole block: if "leaves_first" is false, the reader
      does not turn into the one who walks away three sentences later.
    - `way_out_text` — take the computed way out and show it in ordinary life:
      what to notice, what to say, what to do this week. Concrete, small, doable.
    - `safety` — say it straight, with no euphemisms: if there is violence in
      the relationship — beating, threats, money kept under control, being cut
      off from friends and family — it is NOT a loop, NOT a chart pattern and
      NOT something astrology can work with. Name it plainly. Then support the
      reader warmly and give one concrete piece of advice: talk to someone they
      trust, or reach professional help. Do not lecture, do not frighten, do not
      assume it is happening to them.

    Length: loop_scene 4–6 sentences, break_scene and roles 3–4 sentences each,
    way_out_text 3–5 sentences, safety 3–4 sentences, closing 2 sentences.
    """,
).strip()

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}"


def _partner_gender(gender: str | None) -> str:
    return _PARTNER_GENDER.get(gender or "", _PARTNER_GENDER_NEUTRAL)


def build_user_message(
    result: PainLoopResult,
    *,
    user_name: str | None = None,  # noqa: ARG001 — имя подставляет код, модель его не видит
    gender: str | None = None,
) -> str:
    """Данные для модели: посчитанная петля + точка слома + выход + факторы."""
    payload = {
        # Пол самого человека: по нему PERSONA согласует род во всём тексте.
        "gender": gender or "unknown",
        "partner_gender": _partner_gender(gender),
        "your_age": result.age,
        "leaves_first": result.leaves_first,
        "loop": result.loop,
        "loop_means": result.tagline,
        "break_point": result.break_point,
        "way_out": result.way_out,
        "birth_time_known": result.factors.has_time,
        # Факторы по-русски: они попадают в ответ как есть.
        "chart_factors": result.factors.notes,
    }
    schema_hint = dedent(
        """\
        Response schema (JSON):
        {
          "opening": "...",
          "loop_scene": "...",
          "signs": ["...", "...", "..."],
          "break_scene": "...",
          "roles": "...",
          "way_out_text": "...",
          "safety": "...",
          "closing": "..."
        }
        """,
    ).strip()
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"Computed data:\n{data}\n\n"
        f"The signs array holds exactly {_SIGNS_EXPECTED} items.\n"
        f"The loop is «{result.loop}» and it cannot be changed.\n"
        f"Remember: all string values in Russian, opening and closing start lowercase.\n\n"
        f"{schema_hint}"
    )


def card_caption(result: PainLoopResult) -> str:
    """Подпись под карточкой: петля и её смысл, без разбора."""
    return (
        f"<b>{html.escape(result.loop)}</b> — {html.escape(result.tagline)}.\n"
        "Вот какой круг показывает твоя карта."
    )


def render_answer(
    answer: PainLoopAnswer,
    result: PainLoopResult,
    *,
    user_name: str | None = None,
) -> str:
    """HTML разбора для Telegram. Имя и посчитанное подставляет код."""
    from astra.ask.naming import address, sentence

    blocks: list[str] = [
        html.escape(address(answer.opening, user_name)),
        "",
        f"🔁 <b>{html.escape(result.loop)}</b> — {html.escape(result.tagline)}",
        "",
        html.escape(sentence(answer.loop_scene)),
        "",
        "<i>Узнаёшь по этому:</i>",
        *[f"• {html.escape(sentence(sign))}" for sign in answer.signs],
        "",
        "💔 <b>Где всё ломается</b>",
        # Точку слома посчитал Python — она идёт как есть, модель её разворачивает.
        f"<i>{html.escape(result.break_point)}</i>",
        html.escape(sentence(answer.break_scene)),
        "",
        "⚖️ <b>Что делаешь ты, а что делают с тобой</b>",
        html.escape(sentence(answer.roles)),
        "",
        "🔑 <b>Как разомкнуть круг</b>",
        f"<i>{html.escape(result.way_out)}</i>",
        html.escape(sentence(answer.way_out_text)),
        "",
        "💜 <b>Отдельно и честно</b>",
        html.escape(sentence(answer.safety)),
        "",
        html.escape(address(answer.closing, user_name)),
    ]
    if not result.factors.has_time:
        blocks.extend(
            [
                "",
                "<i>Время рождения неизвестно — считала по Венере, Луне и их аспектам, "
                "без домов. Впишешь время в профиле — разбор станет точнее.</i>",
            ],
        )
    return "\n".join(blocks)
