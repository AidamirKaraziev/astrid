"""Фикстуры промпта совместимости: эталонная пара Айдамир × Анжела."""

from __future__ import annotations

from datetime import date

from astra.llm.schemas.compatibility import (
    CompatibilityPersonInput,
    CompatibilityPromptInput,
    SynastryAspectInput,
)


def build_aidamir_angela_prompt_input() -> CompatibilityPromptInput:
    person_a = CompatibilityPersonInput(
        name="Айдамир",
        gender="мужчина",
        birth_date=date(1998, 2, 14),
        birth_time="03:35",
        birth_place="Армавир",
        timezone="Europe/Moscow",
        accuracy_tier=100,
        natal={
            "sun": "Водолей",
            "moon": "Дева",
            "asc": "Стрелец",
            "mercury": "Водолей",
            "venus": "Козерог",
            "mars": "Рыбы",
            "jupiter": "Рыбы",
            "saturn": "Овен",
        },
    )
    person_b = CompatibilityPersonInput(
        name="Анжела",
        gender="женщина",
        birth_date=date(2001, 12, 2),
        birth_time="03:00",
        birth_place="Станица Старовеличковская",
        timezone="Europe/Moscow",
        accuracy_tier=100,
        natal={
            "sun": "Стрелец",
            "moon": "Близнецы",
            "asc": "Весы",
            "mercury": "Стрелец",
            "venus": "Скорпион",
            "mars": "Водолей",
            "jupiter": "Рак",
            "saturn": "Близнецы",
        },
    )
    aspects = [
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Солнце",
            aspect="соединение",
            to_person="Анжела",
            to_point="Марс",
            orb_deg=0.13,
            theme="сильное притяжение, он зажигает её инициативу",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Луна",
            aspect="квадрат",
            to_person="Анжела",
            to_point="Луна",
            orb_deg=0.29,
            theme="разный эмоциональный ритм, быт и настроение",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Солнце",
            aspect="трин",
            to_person="Анжела",
            to_point="Луна",
            orb_deg=1.09,
            theme="эмоциональный контакт, он понятен её чувствам",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Марс",
            aspect="трин",
            to_person="Анжела",
            to_point="Юпитер",
            orb_deg=1.16,
            theme="энергия, поддержка, совместные планы",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Сатурн",
            aspect="квадрат",
            to_person="Анжела",
            to_point="Юпитер",
            orb_deg=2.28,
            theme="разный темп роста, ожидания vs свобода",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Юпитер",
            aspect="квадрат",
            to_person="Анжела",
            to_point="Венера",
            orb_deg=2.87,
            theme="разные представления о нежности и удовольствии",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Марс",
            aspect="квадрат",
            to_person="Анжела",
            to_point="Сатурн",
            orb_deg=3.84,
            theme="границы, терпение, давление в действиях",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Солнце",
            aspect="квадрат",
            to_person="Анжела",
            to_point="Венера",
            orb_deg=4.31,
            theme="разный язык любви, нужно учиться просить и дарить",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Сатурн",
            aspect="секстиль",
            to_person="Анжела",
            to_point="Сатурн",
            orb_deg=4.96,
            theme="общее чувство ответственности, можно строить долго",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Меркурий",
            aspect="трин",
            to_person="Анжела",
            to_point="Луна",
            orb_deg=5.32,
            theme="лёгкий разговор, слова попадают в настроение",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Венера",
            aspect="оппозиция",
            to_person="Анжела",
            to_point="Юпитер",
            orb_deg=5.45,
            theme="щедрость vs сдержанность в отношениях",
        ),
        SynastryAspectInput(
            from_person="Айдамир",
            from_point="Луна",
            aspect="секстиль",
            to_person="Анжела",
            to_point="Венера",
            orb_deg=5.69,
            theme="нежность через заботу о мелочах",
        ),
    ]
    return CompatibilityPromptInput(person_a=person_a, person_b=person_b, aspects=aspects)
