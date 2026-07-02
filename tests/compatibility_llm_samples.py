"""Общие фикстуры raw-контента для тестов совместимости."""

from __future__ import annotations

from astra.llm.prompts.compatibility_fixtures import build_aidamir_angela_prompt_input
from astra.llm.schemas.compatibility_raw import AspectInterpretationRaw, CompatibilityContentRaw


def sample_interpretations(count: int) -> list[AspectInterpretationRaw]:
    return [
        AspectInterpretationRaw(
            headline=f"Заголовок аспекта {idx}",
            body=(
                f"Наблюдение по аспекту {idx}. "
                "В быту это проявляется в разном темпе и ожиданиях — назовите это вслух."
            ),
        )
        for idx in range(count)
    ]


def sample_content_raw(**overrides) -> CompatibilityContentRaw:  # noqa: ANN003
    prompt_input = build_aidamir_angela_prompt_input()
    count = len(prompt_input.aspects)
    base = {
        "tldr": (
            "Между вами сильное притяжение и живой диалог. "
            "Главная задача — договориться о бытовых ритмах без обвинений."
        ),
        "pair_story": (
            "Вы встречаетесь на стыке идей и чувств.\n\n"
            "В конфликте один тянет к решению, другой — к проговориванию эмоций.\n\n"
            "Сильная сторона — вы не обесцениваете друг друга, даже споря."
        ),
        "natal_insight": (
            "Воздух + огонь: союз идей и движения. "
            "Луна Дева ↔ Близнецы — разный быт, общий запрос на ясность."
        ),
        "metrics": [0.92, 0.68, 0.82, 0.75],
        "aspect_interpretations": sample_interpretations(count),
        "zone_items": [
            ["Солнце–Марс: притяжение", "Солнце–Луна: понимание", "Меркурий–Луна: лёгкий диалог"],
            ["Луна–Луна: бытовые ритмы", "Сатурн–Юпитер: темп", "Солнце–Венера: язык любви"],
            ["Сатурн–Сатурн: обязательства", "Луна–Венера: нежность", "Венера в Козероге: надёжность"],
        ],
        "conclusion_quote": (
            "Химия здесь реальная — её не нужно создавать. "
            "Задача пары: переводить внутренние языки друг другу в быту и заботе."
        ),
        "conclusion_tip": "Один вечер без телефонов — расскажите, что для вас значит «меня любят».",
    }
    base.update(overrides)
    return CompatibilityContentRaw(**base)
