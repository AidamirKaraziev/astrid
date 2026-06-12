"""Fallback-прогноз, если Ollama недоступна."""

from __future__ import annotations

from astra.astro.schemas import AstroContext
from astra.llm.prompts.astrid import day_number_for_date

_COLORS_BY_SUN: dict[str, str] = {
    "Овен": "алый",
    "Телец": "изумрудный",
    "Близнецы": "жёлтый",
    "Рак": "жемчужный",
    "Лев": "золотой",
    "Дева": "оливковый",
    "Весы": "нежно-розовый",
    "Скорпион": "бордовый",
    "Стрелец": "фиолетовый",
    "Козерог": "графитовый",
    "Водолей": "электрик",
    "Рыбы": "морской волны",
}


def body_from_context(ctx: AstroContext, *, name: str | None = None) -> str:
    """Структурированный прогноз в формате Astrid v2 без LLM."""
    sun = (ctx.natal.get("sun") or "").strip()
    moon = (ctx.natal.get("moon") or "").strip()
    display_name = (name or "").strip()

    if sun and moon:
        core_1 = (
            f"твоё Солнце в {sun} задаёт направление дня, "
            f"а Луна в {moon} подсказывает, как ты это проживёшь эмоционально"
        )
    elif sun:
        core_1 = f"твоё Солнце в {sun} подсказывает, куда направить внимание"
    else:
        core_1 = "лучше держать один фокус и не распыляться"

    if display_name:
        sentence_1 = f"{display_name}, сегодня {core_1}."
    else:
        sentence_1 = f"Сегодня {core_1[0].upper()}{core_1[1:]}." if core_1 else "Сегодня держи один фокус."

    if ctx.transits:
        main = ctx.transits[0]
        theme = (main.theme or "фокус дня").strip()
        planet = main.transit_planet
        aspect = main.aspect
        sentence_2 = (
            f"Сильнее всего сейчас {planet} в аспекте «{aspect}» к твоей карте — "
            f"тема дня: {theme}."
        )
    else:
        sentence_2 = "День спокойный: есть пространство разобраться с приоритетами без спешки."

    sentence_3 = (
        "В отношениях пригодится честный, но спокойный разговор — без давления. "
        "На работе и с деньгами двигайся шаг за шагом: один приоритет и доведи его до конца."
    )
    sentence_4 = (
        "Береги силы — короткая прогулка или пауза без экрана помогут вернуть ясность "
        "и выбрать следующий шаг."
    )

    body = f"{sentence_1} {sentence_2} {sentence_3} {sentence_4}"

    number = day_number_for_date(ctx.date, sun or None)
    color = _COLORS_BY_SUN.get(sun, "голубой")
    advice = "Выбери одно важное дело и доведи его до конца."

    return (
        f"✨ Прогноз дня\n\n{body}\n\n"
        f"💡 Совет дня:\n"
        f"{advice}\n\n"
        f"🔢 Число дня:\n{number}\n\n"
        f"🎨 Цвет дня:\n{color}"
    )
