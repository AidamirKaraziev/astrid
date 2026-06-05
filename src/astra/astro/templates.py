"""Fallback-прогноз, если Ollama недоступна."""

from __future__ import annotations

from astra.astro.schemas import AstroContext
from astra.text.ru_inflect import inflect_name

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
    """Структурированный прогноз в формате Astrid без LLM."""
    sun = (ctx.natal.get("sun") or "").strip()
    moon = (ctx.natal.get("moon") or "").strip()
    display_name = (name or "").strip()
    name_dative = inflect_name(display_name, "datv") if display_name else None

    if ctx.transits:
        main = ctx.transits[0]
        theme = (main.theme or "внутренний фокус").strip()
        if name_dative:
            transit_bit = (
                f"{name_dative}, сегодня на первый план выходит «{theme}» — "
                "это может проявиться уже с утра."
            )
        else:
            transit_bit = (
                f"Сегодня на первый план выходит «{theme}» — "
                "это может проявиться уже с утра."
            )
    else:
        transit_bit = "День спокойный: лучше не распыляться и держать один фокус."

    if sun:
        sun_bit = f"Твоё Солнце в {sun} подсказывает, куда направить внимание"
    else:
        sun_bit = "Карта подсказывает, куда направить внимание"
    moon_bit = f", а Луна в {moon} добавляет эмоциональную глубину" if moon else ""

    body = (
        f"{sun_bit}{moon_bit}. {transit_bit} "
        "В отношениях пригодится честный, но спокойный разговор — без давления. "
        "На работе и с деньгами двигайся шаг за шагом: один приоритет и доведи его до конца. "
        "Короткая прогулка или пауза без экрана помогут вернуть ясность."
    )

    number = (ctx.date.day + ctx.date.month + (ord(sun[:1]) if sun else 0)) % 98 + 1
    color = _COLORS_BY_SUN.get(sun, "голубой")
    advice = (
        f"{name_dative}, выбери одно важное дело и доведи его до конца."
        if name_dative
        else "Выбери одно важное дело и доведи его до конца."
    )

    return (
        f"✨ Прогноз дня\n\n{body}\n\n"
        f"💡 Совет дня:\n"
        f"{advice}\n\n"
        f"🔢 Число дня:\n{number}\n\n"
        f"🎨 Цвет дня:\n{color}"
    )
