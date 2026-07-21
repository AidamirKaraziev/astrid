"""Продукт «Карта дня»: прогноз на день, который карта даёт по трём сферам.

Заменяет ежедневное астро-предсказание. Карта ведущая, транзиты дня — контекст:
человек утром видит карту с картинкой, по кнопке получает прогноз. Формат жёсткий
(суть дня → дела → отношения → энергия → шаг), поэтому вывод модели —
структурированный JSON, как у платных раскладов ([[tarot_spreads/base.py]]).
"""

from __future__ import annotations

import html
import json
from datetime import date as date_type
from textwrap import dedent

from pydantic import BaseModel, Field

from astra.llm.prompts.tarot_spreads.base import PERSONA, parse_json_into
from astra.tarot.card import TarotCard

RU_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

# Минимальные/максимальные длины: суть дня должна читаться одним взглядом,
# сферы — быть содержательными, шаг — оставаться одним действием.
_ESSENCE_MIN, _ESSENCE_MAX = 20, 120
_SPHERE_MIN = 60
_STEP_MIN, _STEP_MAX = 15, 180


class DayCardReading(BaseModel):
    essence: str = Field(description="суть дня одной строкой — то, что читается одним взглядом")
    affairs: str = Field(description="дела, работа, деньги")
    relations: str = Field(description="отношения и разговоры")
    energy: str = Field(description="силы, тело, настроение")
    step: str = Field(description="один конкретный шаг сегодня")


_METHOD = dedent(
    """\
    Product: "Card of the day" — the free daily forecast of the bot. One card is
    drawn in the morning; the person taps a button and gets the day read THROUGH
    that card. The card leads, today's transits are supporting context.

    CRITICAL LANGUAGE RULE: write every JSON string VALUE in RUSSIAN (Cyrillic)
    only. Keep the JSON keys exactly as given below (in English).

    Method:
    1. Everything you write comes from THIS card applied to THIS day. Do not
       retell the card's generic meaning and do not write a horoscope that would
       fit any card.
    2. If the data contains transits (Moon, main transit, conflict of the day),
       tie the card to them where they genuinely echo each other — one such link
       is enough, do not list astronomy.
    3. If the data has no chart (field "примечание" says so), read the day purely
       through the card, without houses and personal transits.
    4. Honest and warm: a hard card names the difficulty and shows the way to
       carry it. No fear, no fatalism, no promises of luck.
    5. Match the client's grammatical gender (field "пол"): женщина -> feminine
       forms, мужчина -> masculine, unknown -> phrase it gender-neutrally.

    FIXED STRUCTURE. Return JSON with EXACTLY these five fields, in this order:

    1) essence (Суть дня). ONE short sentence, up to 90 characters, that a person
       grasps at a glance: the mood of the day in the card's voice. No preamble,
       no card name, no "сегодня" as an opening word if it can be avoided.
    2) affairs (Дела). 2 sentences: work, tasks, money — what works today and
       what to avoid, in the card's logic.
    3) relations (Отношения). 2 sentences: people, conversations, closeness.
    4) energy (Энергия). 2 sentences: strength, body, mood, timing inside the day
       (use the Moon timing if it is present in the data).
    5) step (Один шаг). ONE sentence: a concrete action doable today. Not advice
       in general ("будь собой"), but an action ("напиши тому, кто ждёт ответа").

    Each field contains ONLY the meaning of its own sphere: no greetings, no name,
    no card name, no transitions like «а теперь про отношения».

    JSON schema (return exactly these fields, in this order; VALUES IN RUSSIAN):
    {
      "essence": "one short sentence, the mood of the day",
      "affairs": "2 sentences about work and money",
      "relations": "2 sentences about people and conversations",
      "energy": "2 sentences about strength and timing",
      "step": "one sentence: a concrete action today"
    }

    How the user sees the final message (the emoji, the card name and the labels
    are added by us — do NOT write them yourself):
    🎴 <card> · 22 июля
    Суть дня: [essence]
    💼 Дела — [affairs]
    ❤️ Отношения — [relations]
    ⚡ Энергия — [energy]
    → Один шаг: [step]
    """,
)

SYSTEM_PROMPT = f"{PERSONA}\n\n{_METHOD}".strip()

MAX_TOKENS = 700


def _card_payload(card: TarotCard) -> dict:
    return {
        "название": card.name_ru,
        "ключи": list(card.keywords),
        "астро_соответствие": card.astro_affinity,
        "голос_карты": card.voice,
    }


def _astro_payload(astro_context: dict) -> dict:
    """Транзиты дня из prediction.astro_context (схема v2) или общий знак (zodiac)."""
    payload: dict = {}
    if astro_context.get("schema_version") == 2:
        if astro_context.get("conflict"):
            payload["развилка_дня"] = astro_context["conflict"]
        if astro_context.get("main_transit"):
            main = astro_context["main_transit"]
            payload["главный_транзит"] = (
                f"{main.get('transit_planet')} {main.get('aspect')} "
                f"{main.get('natal_point')} (орб {main.get('orb_deg')}°)"
            )
        moon = astro_context.get("moon") or {}
        if moon:
            payload["луна"] = {"знак": moon.get("sign"), "фаза": moon.get("phase")}
            if moon.get("sign_change"):
                payload["луна"]["смена_знака"] = moon["sign_change"]
        if astro_context.get("activated_natal_aspects"):
            payload["натальные_связки"] = [
                f"{a.get('p1')} {a.get('aspect')} {a.get('p2')}"
                for a in astro_context["activated_natal_aspects"]
            ]
        if not astro_context.get("has_time", True):
            payload["примечание"] = "время рождения неизвестно: дома не упоминай"
    elif astro_context.get("schema_version") == "zodiac":
        payload["знак"] = astro_context.get("sign")
        if astro_context.get("moon_note"):
            payload["луна"] = astro_context["moon_note"]
        payload["примечание"] = (
            "натальной карты нет: читай день через карту и знак, без личных домов"
        )
    else:
        payload["примечание"] = "транзитов на сегодня нет: читай день только по карте"
    return payload


def build_user_message(
    card: TarotCard,
    astro_context: dict,
    *,
    user_name: str | None = None,
    gender: str | None = None,
) -> str:
    payload: dict = {}
    client: dict = {}
    if user_name:
        client["имя"] = user_name  # только контекст, обращаться по имени нельзя
    if gender:
        client["пол"] = gender
    if client:
        payload["клиент"] = client
    payload["карта"] = _card_payload(card)
    payload["небо_дня"] = _astro_payload(astro_context or {})
    return "Данные карты дня:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def parse(raw: str) -> DayCardReading | None:
    data = parse_json_into(DayCardReading, raw)
    return data if isinstance(data, DayCardReading) else None


def validate(data: DayCardReading) -> str | None:
    """None — валидно, иначе причина для retry."""
    essence = data.essence.strip()
    if not _ESSENCE_MIN <= len(essence) <= _ESSENCE_MAX:
        return "invalid_essence"
    for name in ("affairs", "relations", "energy"):
        if len(str(getattr(data, name)).strip()) < _SPHERE_MIN:
            return f"field_{name}_too_short"
    step = data.step.strip()
    if not _STEP_MIN <= len(step) <= _STEP_MAX:
        return "invalid_step"
    return None


def _header(card: TarotCard, target: date_type, astro_context: dict) -> list[str]:
    lines = [f"{card.emoji} <b>{card.name_ru} · {target.day} {RU_MONTHS_GENITIVE[target.month - 1]}</b>"]
    ctx = astro_context or {}
    moon = ctx.get("moon") or {}
    if ctx.get("schema_version") == 2 and moon.get("sign"):
        from astra.astro.constants import SIGN_RU_PREPOSITIONAL

        sign = SIGN_RU_PREPOSITIONAL.get(str(moon["sign"]), str(moon["sign"]))
        note = f"🌙 Луна в {sign}"
        if moon.get("phase"):
            note += f", {moon['phase']}"
        lines.append(note)
    elif ctx.get("schema_version") == "zodiac" and ctx.get("moon_note"):
        lines.append(f"🌙 {html.escape(str(ctx['moon_note']))}")
    return lines


def render(
    card: TarotCard,
    target: date_type,
    astro_context: dict,
    data: DayCardReading,
) -> str:
    """Готовое HTML-сообщение: шапка → суть дня → три сферы → один шаг."""
    lines = _header(card, target, astro_context)
    lines += [
        "",
        f"<b>Суть дня: {html.escape(data.essence.strip())}</b>",
        "",
        f"💼 <b>Дела</b> — {html.escape(data.affairs.strip())}",
        f"❤️ <b>Отношения</b> — {html.escape(data.relations.strip())}",
        f"⚡ <b>Энергия</b> — {html.escape(data.energy.strip())}",
        "",
        f"→ <b>Один шаг:</b> {html.escape(data.step.strip())}",
    ]
    return "\n".join(lines)
