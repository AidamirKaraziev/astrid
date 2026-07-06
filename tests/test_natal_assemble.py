"""Round-trip тесты LLM-контракта натала: карта → prompt → assemble → PDF."""

from datetime import date, datetime

import pytest

from astra.astro.calculator import kerykeion_available

pytestmark = pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")


@pytest.fixture(scope="module")
def chart():
    from astra.astro.calculator import build_full_natal_chart

    return build_full_natal_chart(
        name="Тест",
        birth_date=date(1990, 6, 15),
        birth_time=datetime(1990, 6, 15, 14, 30),
        lat=55.7558,
        lon=37.6176,
        timezone="Europe/Moscow",
    )


@pytest.fixture(scope="module")
def chart_no_time():
    from astra.astro.calculator import build_full_natal_chart

    return build_full_natal_chart(
        name="Тест",
        birth_date=date(1990, 6, 15),
        birth_time=None,
        lat=55.7558,
        lon=37.6176,
        timezone="Europe/Moscow",
    )


def _prompt_input(chart):
    from astra.astro.chart_features import build_chart_features
    from astra.llm.natal_assemble import build_natal_prompt_input

    return build_natal_prompt_input(
        chart,
        build_chart_features(chart),
        name="Айдамир",
        gender="м",
        birth_date=date(1990, 6, 15),
        birth_time_label="14:30" if chart.has_time else None,
        birth_place="Москва",
    )


def _content_raw(prompt_input, *, with_asc: bool):
    from astra.llm.schemas.compatibility_raw import AspectInterpretationRaw
    from astra.llm.schemas.natal_raw import NatalContentRaw, SphereTextRaw

    n = len(prompt_input.aspects)
    long_text = "Это осмысленный текст про фактор карты, достаточно длинный для лимитов схемы."
    return NatalContentRaw(
        tldr="Карта про слово, которое становится делом: учись, учи и строй фундамент.",
        core_story=(
            "Первый абзац портрета с фактором карты и деталями, чтобы пройти лимит.\n\n"
            "Второй абзац про внутренний конфликт между знаками и домами.\n\n"
            "Третий абзац про суперсилу с конкретным аспектом."
        ),
        metrics=[0.78, 0.64, 0.9, 0.7],
        sun_text=long_text,
        moon_text=long_text,
        asc_text=long_text if with_asc else None,
        mercury_text=long_text,
        venus_text=long_text,
        mars_text=long_text,
        aspect_interpretations=[
            AspectInterpretationRaw(
                headline=f"Заголовок аспекта {i}",
                body="Наблюдение и что это значит в жизни, две фразы с деталями.",
            )
            for i in range(n)
        ],
        spheres=[
            SphereTextRaw(text=long_text, tip="Сделай один конкретный шаг на неделе."),
            SphereTextRaw(text=long_text, tip="Назови желание прямо в разговоре."),
            SphereTextRaw(text=long_text, tip="Открой отдельный счёт для свободы."),
        ],
        north_node_text=long_text,
        south_node_text=long_text,
        lilith_text=long_text,
        zone_items=[
            ["Меркурий в обители: слово", "Марс в Овне: смелость", "Трин: влияние"],
            ["Квадрат: новизна vs покой", "Стеллиум: корни", "Лилит: доверие"],
            ["Венера: вкус к жизни", "Луна: ритуалы", "9 дом: учёба"],
        ],
        practical_tips=[
            "Заведи файл идей и раз в неделю выбирай одну.",
            "Проведи вечер без экранов.",
            "Спланируй короткое путешествие.",
        ],
        balance_note="Воздух и кардинальный крест доминируют: инициатива через слово.",
        conclusion_quote=(
            "Карта не просит выбирать между свободой и фундаментом — она просит "
            "построить фундамент, с которого удобно взлетать."
        ),
        conclusion_tip="Каждое утро записывай одну идею и один шаг.",
    )


def test_prompt_input_from_real_chart(chart):
    prompt_input = _prompt_input(chart)
    assert prompt_input.person.has_time
    assert prompt_input.asc_sign == "Весы"
    assert len(prompt_input.aspects) == 12  # топ-12 по орбу
    orbs = [a.orb_deg for a in prompt_input.aspects]
    assert orbs == sorted(orbs)
    assert any("Стеллиум" in line for line in prompt_input.feature_lines)
    sun = prompt_input.point("Sun")
    assert sun is not None and sun.house == 9


def test_assemble_full_roundtrip(chart):
    from astra.llm.natal_assemble import assemble_llm_output
    from astra.reports.natal.mapper import llm_output_to_report_data

    prompt_input = _prompt_input(chart)
    output = assemble_llm_output(_content_raw(prompt_input, with_asc=True), prompt_input)

    assert len(output.personality) == 3  # Солнце, Луна, ASC
    assert output.personality[2].title == "Асцендент в Весах"
    assert len(output.mind_feelings_action) == 3
    assert len(output.strong_aspects) + len(output.working_aspects) == 12
    assert all(float(a.orb) < 2.0 for a in output.strong_aspects)
    assert all(2.0 <= float(a.orb) <= 8.0 for a in output.working_aspects)
    assert output.accuracy_note == ""
    # заголовки карточек собраны кодом из фактов
    sun_card = output.personality[0]
    assert sun_card.title == "Солнце в Близнецах · 9 дом"
    mercury = output.mind_feelings_action[0]
    assert mercury.caption == "обитель"

    report = llm_output_to_report_data(
        output, chart, person_name="Айдамир", person_subtitle="15.06.1990 · 14:30 · Москва"
    )
    assert report.metrics[0].label == "Энергия"
    assert len(report.spheres) == 3
    assert report.zone_blocks[0].title == "Сильные стороны"


def test_assemble_without_time_drops_asc(chart_no_time):
    from astra.llm.natal_assemble import NO_TIME_ACCURACY_NOTE, assemble_llm_output

    prompt_input = _prompt_input(chart_no_time)
    assert prompt_input.asc_sign is None
    output = assemble_llm_output(_content_raw(prompt_input, with_asc=False), prompt_input)
    assert len(output.personality) == 2  # без ASC
    assert output.accuracy_note.startswith(NO_TIME_ACCURACY_NOTE[:30])
    assert "дом" not in output.personality[0].title  # без домов в заголовках


def test_assemble_rejects_wrong_aspect_count(chart):
    from astra.llm.natal_assemble import assemble_llm_output

    prompt_input = _prompt_input(chart)
    raw = _content_raw(prompt_input, with_asc=True)
    raw = raw.model_copy(update={"aspect_interpretations": raw.aspect_interpretations[:-1]})
    with pytest.raises(ValueError, match="aspect_interpretations"):
        assemble_llm_output(raw, prompt_input)


def test_fallback_on_empty_interpretation(chart):
    from astra.llm.natal_assemble import assemble_llm_output
    from astra.llm.schemas.compatibility_raw import AspectInterpretationRaw

    prompt_input = _prompt_input(chart)
    raw = _content_raw(prompt_input, with_asc=True)
    interps = list(raw.aspect_interpretations)
    interps[0] = AspectInterpretationRaw(headline="  ", body=" ")
    raw = raw.model_copy(update={"aspect_interpretations": interps})
    output = assemble_llm_output(raw, prompt_input)
    first = (output.strong_aspects + output.working_aspects)[0]
    assert first.headline.strip()
    assert first.body.strip()


def test_prompt_messages_no_time_forbids_houses(chart_no_time):
    from astra.llm.prompts.natal import build_skeleton_user_message

    prompt_input = _prompt_input(chart_no_time)
    message = build_skeleton_user_message(prompt_input)
    assert "НЕИЗВЕСТНО" in message
    assert "ЗАПРЕЩЕНО упоминать асцендент" in message
    assert '"дом"' not in message  # дома не попадают в JSON точек


def test_polish_merge_preserves_metrics(chart):
    from astra.llm.prompts.natal import assemble_from_pipeline
    from astra.llm.schemas.natal_raw import NatalPolishRaw

    prompt_input = _prompt_input(chart)
    content = _content_raw(prompt_input, with_asc=True)
    polish = NatalPolishRaw(
        tldr="Отполированный итог карты: слово становится делом, фундамент строится.",
        core_story=content.core_story,
        sun_text=content.sun_text,
        moon_text=content.moon_text,
        asc_text=content.asc_text,
        mercury_text=content.mercury_text,
        venus_text=content.venus_text,
        mars_text=content.mars_text,
        aspect_interpretations=content.aspect_interpretations,
        spheres=content.spheres,
        north_node_text=content.north_node_text,
        south_node_text=content.south_node_text,
        lilith_text=content.lilith_text,
        balance_note=content.balance_note,
        conclusion_quote=content.conclusion_quote,
        conclusion_tip=content.conclusion_tip,
    )
    output = assemble_from_pipeline(prompt_input, content, polish)
    assert output.tldr.startswith("Отполированный итог")
    assert [m.value for m in output.metrics] == [0.78, 0.64, 0.9, 0.7]


def test_full_pdf_from_llm_output(tmp_path, chart):
    from astra.llm.natal_assemble import assemble_llm_output
    from astra.reports.natal.builder import NatalPdfBuilder
    from astra.reports.natal.mapper import llm_output_to_report_data

    prompt_input = _prompt_input(chart)
    output = assemble_llm_output(_content_raw(prompt_input, with_asc=True), prompt_input)
    report = llm_output_to_report_data(
        output, chart, person_name="Айдамир", person_subtitle="15.06.1990 · 14:30 · Москва"
    )
    out = tmp_path / "natal_llm.pdf"
    builder = NatalPdfBuilder(str(out), report)
    builder.build()
    assert builder.page_num == builder.total_pages
    assert out.stat().st_size > 10_000
