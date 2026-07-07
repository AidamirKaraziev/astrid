"""Промпт интерпретации карты дня: карта отвечает на конфликт из прогноза."""

from __future__ import annotations

import json
from textwrap import dedent

from astra.tarot.deck import TarotCard

TAROT_SYSTEM_PROMPT = dedent(
    """\
    Ты — Astrid, астролог и таролог в Telegram-боте Astra.
    Утром человек получил прогноз с конфликтом дня и нажал «Спросить карты».
    Выпала карта — твоя задача прочитать её КАК ОТВЕТ на этот конфликт,
    связав значение карты с реальными транзитами дня.

    Метод:
    1. Карта отвечает на развилку из данных (conflict) — не пересказывай
       общее значение карты, а приложи её к этому выбору.
    2. Свяжи карту с небом: у карты есть астрологическое соответствие
       (astro_affinity) и есть транзиты дня — если они перекликаются,
       покажи это («Колесница — карта Рака, а твоя Луна сегодня…»).
    3. Карта может выбрать сторону конфликта, может отказаться выбирать
       (третий путь) — реши по смыслу карты, не по шаблону.
    4. Тон: тёплый, честный, без запугивания и фатализма. Обращение на «ты».
    5. Запрещено: «вибрации», «энергетика», «трансформация», «космос
       подсказывает», «карты никогда не ошибаются».

    Формат ответа (строго, два блока через пустую строку):

    [интерпретация — 3–5 предложений: что карта говорит о развилке
    и как это связано с сегодняшним небом]

    [один шаг — одно предложение, конкретное действие сегодня;
    если в данных есть тайминг Луны — используй его]

    Язык: только русский (кириллица). Без иероглифов и эмодзи.
    """,
).strip()


def _card_payload(card: TarotCard) -> dict:
    return {
        "название": card.name_ru,
        "ключи": list(card.keywords),
        "астро_соответствие": card.astro_affinity,
        "голос_карты": card.voice,
    }


def build_tarot_user_message(card: TarotCard, astro_context: dict) -> str:
    """Контекст: конфликт и транзиты из prediction.astro_context (v2 или zodiac)."""
    payload: dict = {"карта": _card_payload(card)}

    if astro_context.get("schema_version") == 2:
        if astro_context.get("conflict"):
            payload["conflict"] = astro_context["conflict"]
        if astro_context.get("main_transit"):
            main = astro_context["main_transit"]
            payload["главный_транзит"] = (
                f"{main.get('transit_planet')} {main.get('aspect')} "
                f"{main.get('natal_point')} (орб {main.get('orb_deg')}°)"
            )
        moon = astro_context.get("moon") or {}
        if moon:
            payload["луна"] = {
                "знак": moon.get("sign"),
                "фаза": moon.get("phase"),
            }
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
        payload["примечание"] = (
            "общий прогноз по знаку (натальной карты нет): читай карту "
            "через знак и Луну, без личных домов"
        )
        if astro_context.get("moon_note"):
            payload["луна"] = astro_context["moon_note"]
    else:
        payload["примечание"] = "прогноза на сегодня нет — прочитай карту как карту дня"

    return (
        "Прочитай выпавшую карту как ответ на конфликт дня.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def validate_tarot_output(text: str) -> str | None:
    """2 блока: интерпретация + шаг (одно предложение)."""
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if len(blocks) < 2:
        return "invalid_structure"
    interpretation, step = blocks[0], " ".join(blocks[1:])
    if len(interpretation) < 80:
        return "interpretation_too_short"
    if len(step) < 15 or step.count(".") + step.count("!") > 2:
        return "invalid_step"
    return None
