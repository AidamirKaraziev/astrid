from astra.astro.schemas import AstroContext


def body_from_context(ctx: AstroContext) -> str:
    if not ctx.transits:
        return (
            "Сегодня хороший день, чтобы двигаться в своём темпе и прислушиваться к себе — "
            "без резких решений до вечера."
        )
    main = ctx.transits[0]
    if main.aspect == "фон дня":
        return (
            f"Сегодня для {ctx.natal.get('sun', 'тебя')} важен спокойный ритм — "
            "доверься интуиции в мелочах, они подскажут верное направление."
        )
    return (
        f"Сегодня транзитная {main.transit_planet} образует {main.aspect} "
        f"к твоей натальной {main.natal_planet} — день про {main.theme}. "
        "Действуй мягко и осознанно."
    )
