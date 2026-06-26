"""Промпт совместимости: синастрия → JSON под PDF SynastryReportData."""

from __future__ import annotations

import json
import re
from textwrap import dedent

from pydantic import ValidationError

from astra.llm.schemas.compatibility import (
    METRIC_LABELS,
    ZONE_BLOCK_TITLES,
    CompatibilityLlmOutput,
    CompatibilityPersonInput,
    CompatibilityPromptInput,
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

COMPATIBILITY_SYSTEM_PROMPT = dedent(
    """\
    Ты — Astra, астролог для русскоязычной аудитории.
    Пишешь разбор синастрии пары: тепло, без запугивания, с практичными выводами.
    Отвечаешь ТОЛЬКО валидным JSON — без markdown, без пояснений до или после.
    Структура ответа строго соответствует мобильному PDF-отчёту: каждое поле попадает
    в конкретный блок верстки. Не меняй названия полей и не добавляй лишних ключей.
    """
).strip()

# Пример ответа — эталон для модели (совпадает с sample_data.py / PDF).
COMPATIBILITY_OUTPUT_EXAMPLE = {
    "tldr": (
        "Химия между вами реальная — Солнце и Марс сходятся почти идеально. "
        "Главная задача: перевести разные эмоциональные языки, особенно в быту."
    ),
    "natal_insight": (
        "Воздух + огонь: идейный союз. Луна Дева ↔ Близнецы — разный быт, "
        "нужен сознательный договор."
    ),
    "metrics": [
        {"label": "Притяжение", "value": 0.92},
        {"label": "Эмоциональный контакт", "value": 0.68},
        {"label": "Общение", "value": 0.82},
        {"label": "Долгосрочность", "value": 0.75},
    ],
    "strong_aspects": [
        {
            "aspect_type": "соединение",
            "from_planet": "Солнце · Водолей",
            "to_planet": "Марс · Водолей",
            "orb": "0.13",
            "strength": "Очень сильно",
            "headline": "Он «включает» её инициативу",
            "body": (
                "Самый мощный аспект пары. Рядом с ним возникает желание действовать — "
                "притяжение ощущается сразу и телесно."
            ),
        },
    ],
    "working_aspects": [
        {
            "aspect_type": "квадрат",
            "from_planet": "Сатурн · Овен",
            "to_planet": "Юпитер · Рак",
            "orb": "2.28",
            "strength": "Заметно",
            "headline": "Разный темп роста",
            "body": (
                "Он видит риски там, где она видит возможности. "
                "Договаривайтесь о шагах, не о принципах."
            ),
        },
    ],
    "zone_blocks": [
        {
            "title": "Что работает само",
            "items": [
                "Солнце–Марс: притяжение, она активируется рядом с ним",
                "Солнце–Луна: он понятен ей без лишних слов",
                "Меркурий–Луна: разговоры даются легко",
            ],
        },
        {
            "title": "Зоны роста",
            "items": [
                "Луна–Луна: договориться о бытовых ритмах",
                "Сатурн–Юпитер: синхронизировать темп",
                "Солнце–Венера: изучить язык любви друг друга",
            ],
        },
        {
            "title": "Опора пары",
            "items": [
                "Сатурн–Сатурн: оба умеют держать обязательства",
                "Луна–Венера: нежность через маленькие жесты",
                "Его Венера в Козероге: строит и держит слово",
            ],
        },
    ],
    "conclusion_quote": (
        "Химия здесь реальная — её не нужно создавать. Задача пары: научиться переводить "
        "свои внутренние языки друг другу, особенно в быту и в том, что каждый называет заботой."
    ),
    "conclusion_tip": (
        "Один вечер без телефонов — расскажите друг другу, "
        "что для вас значит «меня любят», одним конкретным примером."
    ),
    "working_aspects_intro": "Орб 2–6° — требуют внимания, дают точки роста",
}

COMPATIBILITY_USER_TEMPLATE = dedent(
    """\
    Составь разбор совместимости для этой пары.

    Читатель: {reader_name} (person_a, {reader_gender}). Партнёр: {partner_name} (person_b, {partner_gender}).
    Тип продукта: синастрия пары (оба человека с натальными данными).

    person_a:
    {person_a_json}

    person_b:
    {person_b_json}

    synastry_aspects (меньший orb_deg = сильнее; поле theme — подсказка для интерпретации):
    {synastry_aspects_json}

    accuracy_note: {accuracy_note}

    ---

    Верни JSON для mobile-first PDF. Поля и порядок — строго как в схеме ниже.

    ## Куда попадает каждое поле в PDF

    | Поле JSON | Страница PDF |
    |-----------|--------------|
    | tldr | «Краткий итог» — золотая карточка |
    | metrics | «Краткий итог» — 4 прогресс-бара (подписи фиксированы) |
    | natal_insight | «Натальные данные» — инсайт под картами (карты из person_a/b, не от LLM) |
    | strong_aspects | «Главные аспекты» — карточки с бейджем силы (орб < 2°) |
    | working_aspects | «Рабочие аспекты» — карточки без бейджа (орб 2–6°) |
    | working_aspects_intro | подзаголовок секции рабочих аспектов |
    | zone_blocks | «Итог по зонам» — ровно 3 блока с фиксированными заголовками |
    | conclusion_quote | «ВЫВОД» — цитата в золотой рамке |
    | conclusion_tip | «ВЫВОД» — блок «Практика на неделю» |

    НЕ генерируй: имена, даты, натальные таблицы, цвета, кнопку CTA — они подставляются кодом.

    ## Схема JSON (обязательные ключи)

    {json_schema_description}

    ## Пример одного корректного ответа (сокращённый)

    {json_example}

    ## Правила заполнения

    1. Пиши на «ты» к {reader_name}; про пару — {reader_name} и {partner_name}.
    2. strong_aspects: только аспекты из synastry_aspects с orb_deg < 2.0 (все такие, обычно 2–5 шт.).
    3. working_aspects: только аспекты с orb_deg от 2.0 до 6.0 (все такие из списка).
    4. Не выдумывай аспекты — каждая карточка должна соответствовать строке из synastry_aspects.
    5. aspect_type — только: {aspect_types}.
    6. from_planet / to_planet — формат «{{Планета}} · {{Знак}}», знак возьми из natal person_a/person_b.
    7. orb — строка-число как во входе (без символа °), напр. «0.13».
    8. strength: «Очень сильно» (орб < 0.5), «Сильно» (0.5–1.5), «Заметно» (1.5–2 или 2–4), «Фоновое» (4–6).
    9. headline — до 56 символов; body — 2–3 предложения, до 300 символов.
    10. metrics — ровно 4, подписи СТРОГО по порядку: {metric_labels}. value — float 0.0–1.0.
    11. zone_blocks — ровно 3 блока, заголовки СТРОГО: {zone_titles}. В каждом 3–5 коротких пунктов (до 110 симв.).
    12. tldr — 2–3 предложения; conclusion_quote — 2–3; conclusion_tip — одно конкретное действие.
    13. Без эзотерического клише («вибрации», «трансформация», «космос подсказывает»).
  """
).strip()


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


def _person_payload(person: CompatibilityPersonInput) -> dict:
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


def _json_schema_description() -> str:
  lines = [
      "{",
      '  "tldr": string,                    // PDF: краткий итог',
      '  "natal_insight": string,           // PDF: инсайт под натальными картами',
      '  "metrics": [                       // PDF: 4 прогресс-бара, порядок фиксирован',
      '    {"label": "Притяжение", "value": 0.0-1.0},',
      '    {"label": "Эмоциональный контакт", "value": 0.0-1.0},',
      '    {"label": "Общение", "value": 0.0-1.0},',
      '    {"label": "Долгосрочность", "value": 0.0-1.0}',
      "  ],",
      '  "strong_aspects": [                // PDF: главные аспекты, orb < 2°',
      "    {",
      '      "aspect_type": "соединение|трин|квадрат|секстиль|оппозиция",',
      '      "from_planet": "Солнце · Водолей",',
      '      "to_planet": "Марс · Водолей",',
      '      "orb": "0.13",',
      '      "strength": "Очень сильно|Сильно|Заметно|Фоновое",',
      '      "headline": string,',
      '      "body": string',
      "    }",
      "  ],",
      '  "working_aspects": [               // PDF: рабочие аспекты, orb 2–6°',
      "    /* тот же формат, что strong_aspects */",
      "  ],",
      '  "zone_blocks": [                   // PDF: итог по зонам, 3 блока',
      '    {"title": "Что работает само", "items": ["...", "..."]},',
      '    {"title": "Зоны роста", "items": ["...", "..."]},',
      '    {"title": "Опора пары", "items": ["...", "..."]}',
      "  ],",
      '  "conclusion_quote": string,        // PDF: блок ВЫВОД — цитата',
      '  "conclusion_tip": string,          // PDF: практика на неделю',
      '  "working_aspects_intro": string    // подзаголовок секции (можно оставить по умолчанию)',
      "}",
  ]
  return "\n".join(lines)


def build_compatibility_system_prompt() -> str:
    return COMPATIBILITY_SYSTEM_PROMPT


def build_compatibility_user_message(data: CompatibilityPromptInput) -> str:
    aspects = sorted(data.aspects, key=lambda a: a.orb_deg)
    aspect_types = ", ".join(
        typing_cast_aspect_types(),
    )
    return COMPATIBILITY_USER_TEMPLATE.format(
        reader_name=data.person_a.name,
        reader_gender=data.person_a.gender,
        partner_name=data.person_b.name,
        partner_gender=data.person_b.gender,
        person_a_json=json.dumps(_person_payload(data.person_a), ensure_ascii=False, indent=2),
        person_b_json=json.dumps(_person_payload(data.person_b), ensure_ascii=False, indent=2),
        synastry_aspects_json=json.dumps(
            [a.model_dump() for a in aspects],
            ensure_ascii=False,
            indent=2,
        ),
        accuracy_note=build_accuracy_note(
            data.person_a.accuracy_tier,
            data.person_b.accuracy_tier,
        ),
        json_schema_description=_json_schema_description(),
        json_example=json.dumps(COMPATIBILITY_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2),
        aspect_types=aspect_types,
        metric_labels=", ".join(METRIC_LABELS),
        zone_titles=" → ".join(ZONE_BLOCK_TITLES),
    )


def typing_cast_aspect_types() -> list[str]:
    return ["соединение", "трин", "квадрат", "секстиль", "оппозиция"]


def strip_json_fences(raw: str) -> str:
    text = raw.strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    # иногда модель оборачивает в один объект с текстом до/после
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_compatibility_response(raw: str) -> tuple[CompatibilityLlmOutput | None, str | None]:
    """Распарсить ответ LLM в структуру под PDF."""
    try:
        payload = json.loads(strip_json_fences(raw))
        return CompatibilityLlmOutput.model_validate(payload), None
    except json.JSONDecodeError as exc:
        return None, f"json_invalid: {exc.msg}"
    except ValidationError as exc:
        return None, f"validation: {exc.errors()[0]['msg']}"
