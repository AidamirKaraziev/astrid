import re
from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData, TransitAspect
from astra.llm.prompts.astrid import (
    MAX_BODY_SENTENCES,
    MAX_QUESTION_LEN,
    MIN_BODY_SENTENCES,
    MIN_QUESTION_LEN,
    MIN_SENTENCES,
    QUESTION_ARCHETYPES,
    build_system_prompt,
    build_user_message,
    pick_question_archetype,
    sanitize_prediction_output,
    validate_prediction_output,
)

_TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")

_VALID_BODY = (
    "Аида, сегодня ты можешь почувствовать баланс между делами и желаниями. "
    "Обрати внимание на разговоры с близкими — слова могут звучать острее, чем ты думаешь. "
    "Это хороший момент прояснить свои намерения и выбрать, что действительно важно. "
    "Постарайся не смешивать срочное с главным."
)


def _profile(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "user_id": _TEST_USER_ID,
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


def _valid_raw(
    *,
    question: str = "Что важнее — быть правым или быть близким?",
    body: str = _VALID_BODY,
    advice: str = "Сделай паузу перед разговором, который давно откладываешь.",
) -> str:
    return f"{question}\n\n{body}\n\n{advice}"


def test_system_prompt_astrologer_role() -> None:
    prompt = build_system_prompt()
    assert "Astrid" in prompt
    assert "астролог" in prompt.lower()
    assert str(MIN_SENTENCES) in prompt
    assert str(MIN_BODY_SENTENCES) in prompt
    assert str(MAX_BODY_SENTENCES) in prompt
    assert str(MIN_QUESTION_LEN) in prompt
    assert str(MAX_QUESTION_LEN) in prompt
    assert "вопрос дня" in prompt.lower()
    assert "✨ Прогноз дня" not in prompt
    assert "💡 Совет дня" not in prompt
    assert "именительном" in prompt.lower()
    assert "внутренние процессы" in prompt


def test_pick_question_archetype_is_deterministic() -> None:
    target = date(2026, 6, 14)
    first = pick_question_archetype(_TEST_USER_ID, target)
    second = pick_question_archetype(_TEST_USER_ID, target)
    assert first is second
    assert first in QUESTION_ARCHETYPES


def test_pick_question_archetype_varies_by_user_or_date() -> None:
    target = date(2026, 6, 14)
    by_user = {pick_question_archetype(UUID(int=i), target).id for i in range(1, 50)}
    by_date = {
        pick_question_archetype(_TEST_USER_ID, date(2026, 6, day)).id for day in range(1, 29)
    }
    assert len(by_user) > 1
    assert len(by_date) > 1


def test_user_message_includes_archetype_hint() -> None:
    profile = _profile()
    chart = _chart()
    archetype = pick_question_archetype(profile.user_id, _ctx().date)
    message = build_user_message(_ctx(), profile, chart)
    assert "Тип вопроса дня:" in message
    assert archetype.theme in message
    assert archetype.example in message


def test_user_message_includes_birth_data_without_declensions() -> None:
    profile = _profile()
    chart = _chart()
    message = build_user_message(_ctx(), profile, chart)
    assert "Аида" in message
    assert "Аиде" not in message
    assert "1992-02-11" in message
    assert "14:30" in message
    assert "Москва" in message
    assert '"transit"' in message


def test_sanitize_v3_three_blocks() -> None:
    result = sanitize_prediction_output(_valid_raw())
    parts = result.split("\n\n")
    assert len(parts) == 3
    assert parts[0].endswith("?")
    assert parts[0].startswith("Что важнее")
    assert parts[1].startswith("Аида,")
    assert parts[2].startswith("Сделай паузу")


def test_sanitize_strips_brackets_from_question() -> None:
    raw = _valid_raw(question="[Что ты откладываешь дольше, чем нужно?]")
    result = sanitize_prediction_output(raw)
    assert result.split("\n\n")[0] == "Что ты откладываешь дольше, чем нужно?"


def test_sanitize_strips_legacy_v2_sections() -> None:
    raw = (
        "✨ Прогноз дня\n\n"
        f"{_VALID_BODY}\n\n"
        "💡 Совет дня:\n"
        "Сделай паузу перед разговором.\n\n"
        "🔢 Число дня:\n12\n\n"
        "🎨 Цвет дня:\nсиний"
    )
    result = sanitize_prediction_output(raw)
    assert "💡" not in result
    assert "🔢" not in result
    assert "🎨" not in result
    assert "✨" not in result
    assert result == ""


def test_sanitize_limits_body_to_max_sentences() -> None:
    long_body = " ".join(f"Предложение номер {i} о твоём дне." for i in range(1, 12))
    raw = _valid_raw(body=f"Аида, сегодня {long_body}")
    result = sanitize_prediction_output(raw)
    body = result.split("\n\n")[1]
    assert len(re.split(r"(?<=[.!?…])\s+", body)) <= MAX_BODY_SENTENCES


def test_sanitize_limits_advice_to_one_sentence() -> None:
    raw = _valid_raw(
        advice="Сделай паузу перед разговором. Ещё одно лишнее предложение совета."
    )
    result = sanitize_prediction_output(raw)
    advice = result.split("\n\n")[-1]
    assert advice == "Сделай паузу перед разговором."
    assert "лишнее" not in advice


def test_sanitize_strips_hieroglyphs() -> None:
    raw = _valid_raw(body="Аида, сегодня день 和谐 спокойный. " + _VALID_BODY.split(". ", 1)[1])
    result = sanitize_prediction_output(raw)
    assert "和谐" not in result


def test_sanitize_rewrites_internal_processes_cliche() -> None:
    raw = _valid_raw(
        body=(
            "Аида, сегодня внутренние процессы требуют внимания. "
            "Обрати внимание на разговоры с близкими. "
            "Проясни свои намерения. "
            "Не смешивай срочное с главным."
        ),
    )
    result = sanitize_prediction_output(raw)
    assert "внутренние процессы" not in result.lower()
    assert "фокус дня" in result.lower()


def test_sanitize_returns_empty_without_three_blocks() -> None:
    assert sanitize_prediction_output("Только один блок без структуры.") == ""


def test_validate_accepts_valid_v3_output() -> None:
    cleaned = sanitize_prediction_output(_valid_raw())
    assert validate_prediction_output(cleaned, "Аида") is None


def test_validate_accepts_three_sentence_body() -> None:
    body = (
        "Аида, сегодня день про баланс дел и желаний. "
        "Разговоры с близкими могут быть непростыми. "
        "Выбери, что для тебя действительно важно."
    )
    cleaned = sanitize_prediction_output(_valid_raw(body=body))
    assert validate_prediction_output(cleaned, "Аида") is None


def test_validate_accepts_five_sentence_body() -> None:
    body = (
        "Аида, сегодня день про баланс. "
        "Разговоры могут быть непростыми. "
        "Слушай внимательнее. "
        "Выбери приоритеты. "
        "Не торопись с выводами."
    )
    cleaned = sanitize_prediction_output(_valid_raw(body=body))
    assert validate_prediction_output(cleaned, "Аида") is None


def test_validate_rejects_missing_name() -> None:
    cleaned = sanitize_prediction_output(_valid_raw(body=_VALID_BODY.replace("Аида,", "Марина,")))
    assert validate_prediction_output(cleaned, "Аида") == "missing_name"


def test_validate_rejects_invalid_structure() -> None:
    assert validate_prediction_output("Один блок.", "Аида") == "invalid_structure"


def test_validate_rejects_forbidden_content() -> None:
    cleaned = sanitize_prediction_output(
        _valid_raw(body=_VALID_BODY.replace("баланс", "вас ждут перемены, но баланс")),
    )
    assert validate_prediction_output(cleaned, "Аида") == "forbidden_content"


def test_validate_rejects_legacy_markers() -> None:
    text = _valid_raw() + "\n\n🔢 Число дня: 7"
    assert validate_prediction_output(text, "Аида") == "legacy_format"


def test_golden_output_from_gemma_shape() -> None:
    raw = (
        "[Что важнее — быть правым или быть близким?]\n\n"
        f"{_VALID_BODY}\n\n"
        "Слушай, что просит сердце, а не разум.\n\n"
        "Лишний второй совет для проверки."
    )
    result = sanitize_prediction_output(raw)
    assert result.split("\n\n")[0] == "Что важнее — быть правым или быть близким?"
    assert validate_prediction_output(result, "Аида") is None
