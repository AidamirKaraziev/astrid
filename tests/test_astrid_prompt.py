import re
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.llm.prompts.astrid import (
    MAX_SENTENCES,
    MIN_SENTENCES,
    build_system_prompt,
    build_user_message,
    day_number_for_date,
    sanitize_prediction_output,
)


def _profile(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "display_name": "Аида",
        "birth_date": date(1992, 2, 11),
        "birth_time": datetime(1992, 2, 11, 14, 30, tzinfo=ZoneInfo("Europe/Moscow")),
        "birth_place": "Москва",
        "city": "Москва",
        "timezone": "Europe/Moscow",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _chart() -> NatalChartData:
    return NatalChartData(
        accuracy_tier=100,
        sun_sign="Водолей",
        moon_sign="Рак",
        asc_sign="Весы",
        planets={"Sun": 312.0, "Moon": 98.0},
        timezone="Europe/Moscow",
    )


def _ctx() -> AstroContext:
    return AstroContext(
        date=date(2026, 6, 1),
        accuracy_tier=100,
        natal={"sun": "Водолей", "moon": "Рак", "asc": "Весы"},
        transits=[
            TransitAspect(
                transit_planet="Марс",
                aspect="трин",
                natal_planet="Луна",
                orb_deg=1.1,
                theme="границы и энергия",
            ),
        ],
    )


def test_system_prompt_astrologer_role() -> None:
    prompt = build_system_prompt()
    assert "Astrid" in prompt
    assert "астролог" in prompt.lower()
    assert str(MIN_SENTENCES) in prompt
    assert str(MAX_SENTENCES) in prompt
    assert MIN_SENTENCES == MAX_SENTENCES == 4
    assert "✨ Прогноз дня" in prompt
    assert "💡 Совет дня" in prompt
    assert "именительном" in prompt.lower()
    assert "склонен" not in prompt.lower()
    assert "внутренние процессы" in prompt
    assert "«ты»" in prompt or "на «ты»" in prompt


def test_user_message_includes_birth_data_without_declensions() -> None:
    profile = _profile()
    chart = _chart()
    message = build_user_message(_ctx(), profile, chart)
    assert "Аида" in message
    assert "Аиде" not in message
    assert "склонения" not in message.lower()
    assert "1992-02-11" in message
    assert "14:30" in message
    assert "Москва" in message
    assert "Водолей" in message
    assert "Рак" in message
    assert "Весы" in message
    assert '"transit"' in message
    assert '"orb"' in message
    assert '"theme"' in message


def test_sanitize_adds_header_when_missing() -> None:
    raw = "Сегодня для тебя день спокойный.\n\n💡 Совет дня:\nОтдохни."
    result = sanitize_prediction_output(raw)
    assert "✨" in result or "Прогноз дня" in result


def test_sanitize_preserves_footer_sections() -> None:
    body = "Сегодня для тебя может ощущаться прилив ясности. " * 4
    raw = (
        f"✨ Прогноз дня\n\n{body}\n\n"
        "💡 Совет дня:\nОдин фокус.\n\n🔢 Число дня:\n7\n\n🎨 Цвет дня:\nсиний"
    )
    result = sanitize_prediction_output(raw)
    assert "💡 Совет дня" in result
    assert "🔢 Число дня" in result
    assert "🎨 Цвет дня" in result


def test_sanitize_strips_wrapping_quotes() -> None:
    assert sanitize_prediction_output('"Привет."') == "✨ Прогноз дня\n\nПривет."


def test_sanitize_limits_main_body_to_max_sentences() -> None:
    long_body = " ".join(f"Предложение номер {i} о твоём дне." for i in range(1, 12))
    raw = f"✨ Прогноз дня\n\n{long_body}\n\n💡 Совет дня:\nОтдохни."
    result = sanitize_prediction_output(raw)
    main = result.split("💡")[0]
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", main) if s.strip()]
    assert len(sentences) <= MAX_SENTENCES


def test_sanitize_strips_hieroglyphs() -> None:
    raw = "✨ Прогноз дня\n\nСегодня гармония 和谐 и покой.\n\n💡 Совет дня:\nДышите."
    result = sanitize_prediction_output(raw)
    assert "和谐" not in result
    assert "покой" in result


def test_sanitize_rewrites_internal_processes_cliche() -> None:
    raw = (
        "✨ Прогноз дня\n\n"
        "Сегодня внутренние процессы требуют внимания.\n\n"
        "💡 Совет дня:\nОтдохни."
    )
    result = sanitize_prediction_output(raw)
    assert "внутренние процессы" not in result.lower()
    assert "фокус дня" in result.lower()


def test_sanitize_replaces_biased_day_number_twelve() -> None:
    raw = (
        "✨ Прогноз дня\n\n"
        "Сегодня день спокойный.\n\n"
        "💡 Совет дня:\nОтдохни.\n\n"
        "🔢 Число дня:\n12\n\n"
        "🎨 Цвет дня:\nсиний"
    )
    expected = day_number_for_date(date(2026, 6, 1), "Водолей")
    result = sanitize_prediction_output(
        raw,
        prediction_date=date(2026, 6, 1),
        sun_sign="Водолей",
    )
    assert f"🔢 Число дня:\n{expected}" in result
    assert "🔢 Число дня:\n12" not in result


def test_day_number_for_date_is_deterministic() -> None:
    assert 1 <= day_number_for_date(date(2026, 6, 12), "Лев") <= 99
    assert day_number_for_date(date(2026, 6, 12), "Лев") == day_number_for_date(
        date(2026, 6, 12),
        "Лев",
    )
