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
    assert "✨ Прогноз дня" in prompt
    assert "💡 Совет дня" in prompt
    assert "Общая энергия" in prompt  # в блоке запрета рубрик
    assert "иероглиф" in prompt.lower()
    assert "«ты»" in prompt or "на «ты»" in prompt
    assert "никогда «вы»" in prompt or "не на «вы»" in prompt.lower()
    assert "ритм" in prompt.lower()
    assert "имя" in prompt.lower() or "склонен" in prompt.lower()


def test_user_message_includes_birth_data() -> None:
    profile = _profile()
    chart = _chart()
    message = build_user_message(_ctx(), profile, chart)
    assert "Аида" in message
    assert "Аиде" in message
    assert "склонения имени" in message.lower()
    assert "1992-02-11" in message
    assert "14:30" in message
    assert "Москва" in message
    assert "Водолей" in message
    assert "Рак" in message
    assert "Весы" in message
    assert "transits" in message
    assert str(MIN_SENTENCES) in message
    assert str(MAX_SENTENCES) in message


def test_sanitize_adds_header_when_missing() -> None:
    raw = "Сегодня для тебя день спокойный.\n\n💡 Совет дня:\nОтдохни."
    result = sanitize_prediction_output(raw)
    assert "✨" in result or "Прогноз дня" in result


def test_sanitize_preserves_footer_sections() -> None:
    body = "Сегодня для тебя может ощущаться прилив ясности. " * 20
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
    assert "гармония" in result
    assert "покой" in result


def test_sanitize_rewrites_ritm_cliche() -> None:
    raw = (
        "✨ Прогноз дня\n\n"
        "Сегодня солнечный ритм подскажет тебе ритм дня.\n\n"
        "💡 Совет дня:\nОтдохни."
    )
    result = sanitize_prediction_output(raw)
    assert "ритм" not in result.lower()
    assert "солнечный знак" in result.lower()
