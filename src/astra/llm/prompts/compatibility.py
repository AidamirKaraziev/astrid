"""Промпт совместимости: синастрия → JSON (Split Contract, 3 шага)."""

from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from astra.llm.compatibility_assemble import assemble_llm_output, merge_polish, sorted_aspects
from astra.llm.schemas.compatibility import CompatibilityLlmOutput, CompatibilityPromptInput
from astra.llm.schemas.compatibility_raw import (
    CompatibilityContentRaw,
    CompatibilityNarrativeSkeleton,
    CompatibilityPolishRaw,
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_ModelT = TypeVar("_ModelT", bound=BaseModel)

COMPATIBILITY_SYSTEM_PROMPT = dedent(
    """\
    Ты — Astra, астролог для русскоязычной аудитории.
    Пишешь разбор синастрии: тепло, честно, без запугивания, с практичными выводами.
    Отвечаешь ТОЛЬКО валидным JSON — без markdown, без текста до или после.
    Формат: плоский объект с полями на верхнем уровне.
    Запрещено в ответе: properties, type, description, $schema, items, required — это не JSON Schema, а данные.
    Пиши живо и конкретно: сцены из жизни пары, а не абстрактную эзотерику.
    Избегай клише: «вибрации», «трансформация», «космос подсказывает», «высшие силы».
    """
).strip()

SKELETON_SYSTEM_PROMPT = COMPATIBILITY_SYSTEM_PROMPT + dedent(
    """

    Задача этого шага — скелет нарратива: история пары, напряжение, рост, черновик метрик.
    Не пиши интерпретации аспектов — они будут на следующем шаге.
    """
).strip()

CONTENT_SYSTEM_PROMPT = COMPATIBILITY_SYSTEM_PROMPT + dedent(
    """

    Задача — полный контент отчёта по схеме.
    Не генерируй орбы, типы аспектов, подписи «Планета · Знак», заголовки zone_blocks —
    их подставит код.
    aspect_interpretations[i] строго соответствует аспекту [i] из входного списка.
    """
).strip()

POLISH_SYSTEM_PROMPT = COMPATIBILITY_SYSTEM_PROMPT + dedent(
    """

    Задача — редактор: вычисти шаблонность, усиль конкретику, сохрани факты и имена.
    Не меняй количество элементов в aspect_interpretations.
    metrics и zone_items не трогай — их нет в ответе этого шага.
    """
).strip()


def strip_json_fences(raw: str) -> str:
    text = raw.strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _normalize_llm_payload(payload: object) -> object:
    """Распаковать ответ, если модель вернула JSON Schema вместо данных."""
    if not isinstance(payload, dict):
        return payload

    if "properties" in payload and isinstance(payload["properties"], dict):
        props = payload["properties"]
        if props and not any(
            isinstance(value, dict) and {"type", "anyOf", "allOf"} & set(value.keys())
            for value in props.values()
        ):
            return props

    return payload


def _format_model_fields(model: type[BaseModel]) -> str:
    lines: list[str] = []
    for name, field in model.model_fields.items():
        hint = (field.description or "").strip()
        lines.append(f'- "{name}"' + (f" — {hint}" if hint else ""))
    return "\n".join(lines)


_SKELETON_EXAMPLE = {
    "pair_story": (
        "Вы встречаетесь на стыке идей и чувств — рядом легче рискнуть.\n\n"
        "В конфликте один тянет к решению, другой — к проговариванию эмоций.\n\n"
        "Сильная сторона — вы не гасите друг друга, даже споря."
    ),
    "central_tension": "Разный бытовой ритм Лун: порядок vs свобода.",
    "growth_path": "Договориться о правилах дома и темпе решений.",
    "metrics": [0.88, 0.72, 0.8, 0.76],
}

_CONTENT_EXAMPLE = {
    "tldr": "Химия сильная, главная задача — синхронизировать быт и эмоции.",
    "pair_story": _SKELETON_EXAMPLE["pair_story"],
    "natal_insight": "Воздух + огонь: идейный союз с разным эмоциональным ритмом.",
    "metrics": [0.88, 0.72, 0.8, 0.76],
    "aspect_interpretations": [
        {
            "headline": "Он зажигает её инициативу",
            "body": "Солнце–Марс даёт мгновенное притяжение. В быту это ощущается как желание действовать рядом друг с другом.",
        },
    ],
    "zone_items": [
        ["Солнце–Марс: притяжение", "Меркурий–Луна: лёгкий диалог", "Марс–Юпитер: общие планы"],
        ["Луна–Луна: быт", "Сатурн–Юпитер: темп", "Солнце–Венера: язык любви"],
        ["Сатурн–Сатурн: обязательства", "Луна–Венера: забота", "Опора на общие ценности"],
    ],
    "conclusion_quote": "Химия реальна — задача в переводе эмоциональных языков друг для друга.",
    "conclusion_tip": "Один вечер без телефонов — расскажите, что для вас значит «меня любят».",
}

_POLISH_EXAMPLE = {
    "tldr": "Между вами работает притяжение — учитесь говорить о быте без обвинений.",
    "pair_story": _SKELETON_EXAMPLE["pair_story"],
    "natal_insight": "Воздух и огонь дают движение; Луны просят договор о ритме.",
    "conclusion_quote": "Связь уже есть — углубляйте её через конкретные разговоры о заботе.",
    "conclusion_tip": "Каждый пишет одну фразу: «Сегодня я почувствовал(а) любовь, когда…»",
    "aspect_interpretations": _CONTENT_EXAMPLE["aspect_interpretations"],
}


def _example_json(example: dict) -> str:
    return json.dumps(example, ensure_ascii=False, indent=2)


def _person_payload(person) -> dict:  # noqa: ANN001
    return {
        "name": person.name,
        "gender": person.gender,
        "birth_date": person.birth_date.isoformat(),
        "birth_time": person.birth_time,
        "birth_place": person.birth_place,
        "timezone": person.timezone,
        "accuracy_tier": person.accuracy_tier,
        "natal": person.natal,
    }


def build_accuracy_note(person_a_tier: int, person_b_tier: int) -> str:
    if person_a_tier >= 80 and person_b_tier >= 80:
        return (
            f"person_a={person_a_tier}%, person_b={person_b_tier}% — "
            "можно использовать Луну, ASC и все планеты."
        )
    if person_a_tier >= 50 and person_b_tier >= 50:
        return (
            f"person_a={person_a_tier}%, person_b={person_b_tier}% — "
            "Луна и ASC с оговоркой; не строй вывод только на домах."
        )
    return (
        f"person_a={person_a_tier}%, person_b={person_b_tier}% — "
        "опирайся на Солнце и общие темы; Луну и ASC упоминай осторожно."
    )


def _relationship_label(context: str) -> str:
    return {
        "love": "отношения / романтика",
        "work": "работа / коллеги / деловое партнёрство",
        "friendship": "дружба",
    }.get(context, context)


def _pair_mode_label(mode: str) -> str:
    return {
        "me_partner": "я + партнёр",
        "two_people": "два человека (нейтральный разбор)",
    }.get(mode, mode)


def _context_instructions(
    context: str,
    pair_mode: str,
    reader_name: str,
    partner_name: str,
) -> str:
    focus = {
        "love": (
            "Акцент: притяжение, эмоции, близость, Венера/Марс/Луна, язык любви, "
            "конфликты в паре, долгосрочность. Можно говорить о сексе и расставании честно."
        ),
        "work": (
            "Акцент: роли, границы, Меркурий/Сатурн, доверие, совместные задачи. "
            "Без романтизации; про карьеру и командную динамику."
        ),
        "friendship": (
            "Акцент: поддержка, общие интересы, Луна/Юпитер, лояльность. "
            "Без давления романтики."
        ),
    }.get(context, "")
    if pair_mode == "two_people":
        tone = (
            f"Пиши нейтрально про {reader_name} и {partner_name} (на «они»), "
            "без обращения «ты» к читателю."
        )
    else:
        tone = f"Пиши на «ты» к {reader_name}; про пару — {reader_name} и {partner_name}."
    return f"{focus}\n{tone}"


def _indexed_aspects_json(data: CompatibilityPromptInput) -> str:
    rows = []
    for idx, aspect in enumerate(sorted_aspects(data)):
        row = aspect.model_dump()
        row["index"] = idx
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _shared_context_block(data: CompatibilityPromptInput) -> str:
    return dedent(
        f"""\
        Контекст разбора: {_relationship_label(data.relationship_context)}.
        Режим: {_pair_mode_label(data.pair_mode)}.
        Читатель: {data.person_a.name} (person_a). Партнёр: {data.person_b.name} (person_b).

        {_context_instructions(
            data.relationship_context,
            data.pair_mode,
            data.person_a.name,
            data.person_b.name,
        )}

        person_a:
        {json.dumps(_person_payload(data.person_a), ensure_ascii=False, indent=2)}

        person_b:
        {json.dumps(_person_payload(data.person_b), ensure_ascii=False, indent=2)}

        synastry_aspects (индекс [i] = порядок aspect_interpretations[i]):
        {_indexed_aspects_json(data)}

        accuracy_note: {build_accuracy_note(data.person_a.accuracy_tier, data.person_b.accuracy_tier)}
        """
    ).strip()


def build_skeleton_user_message(data: CompatibilityPromptInput) -> str:
    return dedent(
        f"""\
        Шаг 1: составь скелет нарратива синастрии.

        {_shared_context_block(data)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(CompatibilityNarrativeSkeleton)}

        Пример корректного ответа:
        {_example_json(_SKELETON_EXAMPLE)}

        Правила:
        1. pair_story — 3 абзаца через \\n\\n: как звучит пара → типичный конфликт → сильная сторона.
        2. metrics — 4 числа 0.0–1.0 (притяжение, эмоции, общение, долгосрочность), согласованы с текстом.
        3. central_tension и growth_path — конкретно, с отсылкой к планетам из входа.
        """
    ).strip()


def build_content_user_message(
    data: CompatibilityPromptInput,
    skeleton: CompatibilityNarrativeSkeleton,
) -> str:
    return dedent(
        f"""\
        Шаг 2: полный контент отчёта синастрии.

        {_shared_context_block(data)}

        narrative_skeleton (шаг 1):
        {skeleton.model_dump_json(indent=2)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(CompatibilityContentRaw)}

        Пример структуры (aspect_interpretations — ровно {len(data.aspects)} шт., здесь сокращён):
        {_example_json(_CONTENT_EXAMPLE)}

        Правила:
        1. aspect_interpretations — ровно {len(data.aspects)} объектов, порядок = индексы [0]…[{len(data.aspects) - 1}].
        2. Каждый body: наблюдение + что это значит в быту/конфликте/близости (2–3 предложения).
        3. zone_items — 3 списка по 3–5 коротких пунктов (заголовки блоков подставит код).
        4. metrics — 4 float 0.0–1.0, можно уточнить скелет.
        5. pair_story — уточни скелет, сохрани 3 абзаца через \\n\\n.
        6. conclusion_tip — одно конкретное действие на неделю.
        """
    ).strip()


def build_polish_user_message(
    data: CompatibilityPromptInput,
    content: CompatibilityContentRaw,
) -> str:
    return dedent(
        f"""\
        Шаг 3: отредактируй тексты отчёта — сделай живее и точнее.

        {_shared_context_block(data)}

        draft_content:
        {content.model_dump_json(indent=2)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(CompatibilityPolishRaw)}

        Пример корректного ответа (aspect_interpretations — ровно {len(data.aspects)} шт.):
        {_example_json(_POLISH_EXAMPLE)}

        Правила:
        1. Сохрани факты, имена, количество aspect_interpretations ({len(data.aspects)}).
        2. Убери шаблоны и воду; усиль сцены «когда вы…».
        3. tldr — 2–3 предложения, цепляет с первой строки.
        """
    ).strip()


def build_compatibility_system_prompt() -> str:
    return CONTENT_SYSTEM_PROMPT


def build_compatibility_user_message(data: CompatibilityPromptInput) -> str:
    """Превью промпта шага 2 (контент) без скелета — для scripts/preview."""
    placeholder = CompatibilityNarrativeSkeleton(
        pair_story="(скелет с шага 1)",
        central_tension="(напряжение)",
        growth_path="(рост)",
        metrics=[0.8, 0.7, 0.75, 0.7],
    )
    return build_content_user_message(data, placeholder)


def _parse_model(raw: str, model: type[_ModelT]) -> tuple[_ModelT | None, str | None]:
    try:
        payload = json.loads(strip_json_fences(raw))
        payload = _normalize_llm_payload(payload)
        return model.model_validate(payload), None
    except json.JSONDecodeError as exc:
        return None, f"json_invalid: {exc.msg}"
    except ValidationError as exc:
        return None, f"validation: {exc.errors()[0]['msg']}"


def parse_narrative_skeleton(raw: str) -> tuple[CompatibilityNarrativeSkeleton | None, str | None]:
    return _parse_model(raw, CompatibilityNarrativeSkeleton)


def parse_content_raw(raw: str) -> tuple[CompatibilityContentRaw | None, str | None]:
    parsed, error = _parse_model(raw, CompatibilityContentRaw)
    if parsed is None:
        return None, error
    aspects_count = len(parsed.aspect_interpretations)
    return parsed, error


def parse_polish_raw(raw: str) -> tuple[CompatibilityPolishRaw | None, str | None]:
    return _parse_model(raw, CompatibilityPolishRaw)


def parse_compatibility_response(
    raw: str,
    prompt_input: CompatibilityPromptInput,
) -> tuple[CompatibilityLlmOutput | None, str | None]:
    """Legacy: один JSON → assemble (для тестов и отладки)."""
    content, error = parse_content_raw(raw)
    if content is None:
        return None, error
    if len(content.aspect_interpretations) != len(prompt_input.aspects):
        return None, (
            f"validation: aspect_interpretations len {len(content.aspect_interpretations)} "
            f"!= {len(prompt_input.aspects)}"
        )
    try:
        return assemble_llm_output(content, prompt_input), None
    except (ValidationError, ValueError) as exc:
        return None, f"assemble: {exc}"


def assemble_from_pipeline(
    prompt_input: CompatibilityPromptInput,
    content: CompatibilityContentRaw,
    polish: CompatibilityPolishRaw,
) -> CompatibilityLlmOutput:
    if len(polish.aspect_interpretations) != len(prompt_input.aspects):
        msg = "polish aspect_interpretations length mismatch"
        raise ValueError(msg)
    merged = merge_polish(content, polish)
    return assemble_llm_output(merged, prompt_input)
