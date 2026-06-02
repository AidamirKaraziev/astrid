"""Fallback-прогноз, если Ollama недоступна."""

from __future__ import annotations

from astra.astro.schemas import AstroContext

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


def body_from_context(ctx: AstroContext) -> str:
    """Структурированный прогноз в формате Astrid без LLM."""
    sun = (ctx.natal.get("sun") or "").strip()
    moon = (ctx.natal.get("moon") or "").strip()

    if ctx.transits:
        main = ctx.transits[0]
        theme = (main.theme or "внутренний фокус").strip()
        transit_bit = f"Сегодня на первый план выходит «{theme}» — это может ощущаться с самого утра."
    else:
        transit_bit = "День ровный: есть тенденция не распыляться и держать один фокус."

    sun_bit = f"Твой солнечный ритм {sun} задаёт тон" if sun else "Карта задаёт тон"
    moon_bit = f", а Луна в {moon} добавляет эмоциональную глубину" if moon else ""

    body = (
        f"{sun_bit}{moon_bit}. {transit_bit} "
        "В отношениях стоит обратить внимание на честный, но спокойный разговор — без давления. "
        "На работе и с деньгами двигайся шаг за шагом: один приоритет и доведи его до конца. "
        "Энергия дня поддерживает короткую прогулку или паузу без экрана — так вернётся ясность."
    )

    number = (ctx.date.day + ctx.date.month + (ord(sun[:1]) if sun else 0)) % 98 + 1
    color = _COLORS_BY_SUN.get(sun, "голубой")

    return (
        f"✨ Прогноз дня\n\n{body}\n\n"
        f"💡 Совет дня:\n"
        f"Выбери одно важное дело и доведи его до конца — так ты поймаешь ритм дня.\n\n"
        f"🔢 Число дня:\n{number}\n\n"
        f"🎨 Цвет дня:\n{color}"
    )
