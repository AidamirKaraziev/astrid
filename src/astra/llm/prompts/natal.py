"""Промпт разбора натальной карты: карта → JSON (Split Contract, 3 шага).

Методологическое ядро (отличие от конкурентов):
- астрологию считает Python — LLM получает предвычисленные факторы и акценты;
- иерархия значимости: большая тройка > личные планеты > акценты > фон;
- синтез вместо перечисления, противоречия взвешиваются, Barnum-фразы запрещены;
- честность: без времени рождения ASC и дома не упоминаются вовсе.
"""

from __future__ import annotations

import json
from textwrap import dedent

from astra.llm.natal_assemble import assemble_llm_output, merge_polish
from astra.llm.prompts.compatibility import _format_model_fields, _parse_model
from astra.llm.schemas.natal import NatalLlmOutput, NatalPromptInput
from astra.llm.schemas.natal_raw import (
    NatalContentRaw,
    NatalNarrativeSkeleton,
    NatalPolishRaw,
)

NATAL_SYSTEM_PROMPT = dedent(
    """\
    Ты — Astra, профессиональный астролог для русскоязычной аудитории.
    Пишешь разбор натальной карты: тепло, честно, без запугивания и фатализма,
    с практичными выводами. Обращайся к человеку на «ты».
    Отвечаешь ТОЛЬКО валидным JSON — без markdown, без текста до или после.
    Формат: плоский объект с полями на верхнем уровне.
    Запрещено в ответе: properties, type, description, $schema, items, required —
    это не JSON Schema, а данные.

    Метод (обязателен):
    1. Иерархия. Большая тройка (Солнце, Луна, асцендент) > личные планеты
       и их аспекты > акценты карты (планеты на углах, король аспектов,
       стеллиумы, конфигурации) > стихии и кресты > высшие планеты.
       Не подавай фоновый фактор с тем же весом, что ядро.
    2. Синтез, не перечисление. Не описывай планеты по одной — связывай факторы
       между собой. Каждый вывод опирается минимум на один конкретный фактор
       из входных данных, и ты его называешь: «Луна в Козероге в 4 доме»,
       а не «твоя Луна».
    3. Противоречия — это материал. Если факторы спорят (воздушное Солнце против
       Сатурна на асценденте), покажи, как этот спор живёт в человеке,
       а не замалчивай его.
    4. Запрещены утверждения, верные для любого человека: «иногда ты сомневаешься
       в себе», «ты ценишь близких». Каждый абзац должен быть непереносим
       на случайного другого человека — иначе перепиши его.
    5. Пиши сценами из жизни, а не абстракциями. Избегай клише: «вибрации»,
       «трансформация», «космос подсказывает», «энергетика», «кармические уроки»
       без конкретики.
    6. Соблюдай accuracy_note: если время рождения неизвестно — не упоминай
       асцендент и дома вовсе, ни прямо, ни намёком.
    """
).strip()

SKELETON_SYSTEM_PROMPT = NATAL_SYSTEM_PROMPT + dedent(
    """

    Задача этого шага — скелет разбора: центральная тема карты, портрет,
    напряжение, вектор роста, тезисы сфер, черновик метрик.
    Не пиши интерпретации аспектов — они будут на следующем шаге.
    """
).rstrip()

CONTENT_SYSTEM_PROMPT = NATAL_SYSTEM_PROMPT + dedent(
    """

    Задача — полный контент разбора по схеме.
    Не генерируй орбы, названия аспектов, заголовки блоков и подписи
    «Планета · Знак» — их подставит код.
    aspect_interpretations[i] строго соответствует аспекту [i] из входного списка.
    """
).rstrip()

POLISH_SYSTEM_PROMPT = NATAL_SYSTEM_PROMPT + dedent(
    """

    Задача — редактор: вычисти шаблонность и Barnum-фразы (верные для всех),
    усиль конкретику и сцены, сохрани факты и отсылки к факторам карты.
    Не меняй количество элементов в aspect_interpretations и spheres.
    metrics, zone_items и practical_tips не трогай — их нет в ответе этого шага.
    """
).rstrip()


_SKELETON_EXAMPLE = {
    "core_story": (
        "Ты быстро загораешься идеями — Солнце и Меркурий в Близнецах дают речь, "
        "которой доверяют.\n\n"
        "Конфликт: стеллиум в Козероге в 4 доме требует фундамента, а Близнецы "
        "просят движения.\n\n"
        "Суперсила — Марс в Овне в 7 доме: прямота, которая проясняет отношения."
    ),
    "central_tension": "Лёгкость Близнецов против дисциплины Козерога в 4 доме.",
    "growth_path": "Построить свой фундамент, с которого удобно взлетать.",
    "sphere_theses": [
        "Карьера растёт через наставничество — Юпитер на MC.",
        "В отношениях нужен живой диалог — Марс в 7 доме.",
        "Деньги = автономия: Плутон во 2 доме.",
    ],
    "metrics": [0.78, 0.64, 0.9, 0.7],
}

_CONTENT_EXAMPLE = {
    "tldr": "Твоя карта — про слово, которое становится делом: учись и учи, но строй фундамент.",
    "core_story": _SKELETON_EXAMPLE["core_story"],
    "metrics": [0.78, 0.64, 0.9, 0.7],
    "sun_text": "Ядро — любопытство: Солнце в Близнецах в 9 доме зовёт учиться и делиться выводами…",
    "moon_text": "Луна в Рыбах в 6 доме: эмоции приходят волнами и просят тишины и рутины-якоря…",
    "asc_text": "Асцендент в Весах: люди видят дипломата — мягкость открывает двери…",
    "mercury_text": "Меркурий в Близнецах в обители: мышление быстрое и точное…",
    "venus_text": "Венера в Тельце: любишь медленно, глубоко и на своей территории…",
    "mars_text": "Марс в Овне в 7 доме: действуешь рывком и честно…",
    "aspect_interpretations": [
        {
            "headline": "Учитель, который лечит словом",
            "body": "Соединение Юпитера с Хироном: помогая другим почувствовать опору, ты лечишь и свою тоску по дому.",
        }
    ],
    "spheres": [
        {"text": "Карьера растёт там, где ты создаёшь людям опору…", "tip": "Возьми одного ученика на месяц."},
        {"text": "Тебя притягивают самостоятельные партнёры…", "tip": "В споре сначала назови, чего хочешь ты."},
        {"text": "Деньги для тебя — автономия…", "tip": "Открой счёт-«фонд свободы»."},
    ],
    "north_node_text": "Северный узел в Водолее в 4 доме: строить свой дом по своим правилам…",
    "south_node_text": "Южный узел во Льве в 10 доме: привычка ждать аплодисментов…",
    "lilith_text": "Лилит в Скорпионе во 2 доме: контроль через ресурсы…",
    "zone_items": [
        ["Меркурий в обители: слово, которому верят", "Марс в Овне: смелость", "Трин Юпитер-Плутон: влияние"],
        ["Квадрат Солнце-Луна: новизна vs покой", "Стеллиум в 4 доме: корни", "Лилит: доверие в деньгах"],
        ["Венера в Тельце: вкус к жизни", "Луна в 6 доме: ритуалы", "9 дом: учёба как топливо"],
    ],
    "practical_tips": [
        "Заведи файл идей: раз в неделю выбирай одну и делай первый шаг.",
        "Один вечер в неделю без экранов — Луна в Рыбах восстанавливается в тишине.",
        "Спланируй короткое путешествие: 9 дом заряжается от предвкушения.",
    ],
    "balance_note": "Воздух и кардинальный крест доминируют: ты инициируешь через слово.",
    "conclusion_quote": "Карта не просит выбирать между свободой и фундаментом — она просит построить фундамент, с которого удобно взлетать.",
    "conclusion_tip": "Каждое утро записывай одну идею и один шаг к дому мечты.",
}

_POLISH_EXAMPLE = {
    "tldr": _CONTENT_EXAMPLE["tldr"],
    "core_story": _CONTENT_EXAMPLE["core_story"],
    "sun_text": _CONTENT_EXAMPLE["sun_text"],
    "moon_text": _CONTENT_EXAMPLE["moon_text"],
    "asc_text": _CONTENT_EXAMPLE["asc_text"],
    "mercury_text": _CONTENT_EXAMPLE["mercury_text"],
    "venus_text": _CONTENT_EXAMPLE["venus_text"],
    "mars_text": _CONTENT_EXAMPLE["mars_text"],
    "aspect_interpretations": _CONTENT_EXAMPLE["aspect_interpretations"],
    "spheres": _CONTENT_EXAMPLE["spheres"],
    "north_node_text": _CONTENT_EXAMPLE["north_node_text"],
    "south_node_text": _CONTENT_EXAMPLE["south_node_text"],
    "lilith_text": _CONTENT_EXAMPLE["lilith_text"],
    "balance_note": _CONTENT_EXAMPLE["balance_note"],
    "conclusion_quote": _CONTENT_EXAMPLE["conclusion_quote"],
    "conclusion_tip": _CONTENT_EXAMPLE["conclusion_tip"],
}


def _example_json(example: dict) -> str:
    return json.dumps(example, ensure_ascii=False, indent=2)


def build_accuracy_note(prompt_input: NatalPromptInput) -> str:
    if prompt_input.person.has_time:
        return (
            "время рождения известно — используй асцендент, MC, дома и Луну "
            "в полную силу."
        )
    note = (
        "время рождения НЕИЗВЕСТНО — асцендент и дома не рассчитаны. "
        "ЗАПРЕЩЕНО упоминать асцендент, MC и дома. Поле asc_text верни как null."
    )
    if prompt_input.moon_sign_uncertain:
        note += (
            " Луна в этот день меняла знак — говори о ней осторожно, "
            "без категоричных формулировок."
        )
    return note


def _points_json(prompt_input: NatalPromptInput) -> str:
    rows = []
    for p in prompt_input.points:
        row: dict[str, object] = {"планета": p.name, "знак": p.sign, "градус": p.sign_deg}
        if p.house is not None:
            row["дом"] = p.house
        if p.retrograde:
            row["ретроградная"] = True
        if p.dignity:
            row["достоинство"] = p.dignity
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _indexed_aspects_json(prompt_input: NatalPromptInput) -> str:
    rows = []
    for idx, aspect in enumerate(prompt_input.aspects):
        rows.append(
            {
                "index": idx,
                "аспект": f"{aspect.p1} {aspect.aspect} {aspect.p2}",
                "орб": aspect.orb_deg,
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _shared_context_block(prompt_input: NatalPromptInput) -> str:
    person = prompt_input.person
    gender_line = f"Пол: {person.gender}.\n" if person.gender else ""
    angles = ""
    if prompt_input.asc_sign:
        angles = f"Асцендент: {prompt_input.asc_sign}. MC: {prompt_input.mc_sign}.\n"
    features = "\n".join(f"- {line}" for line in prompt_input.feature_lines) or "- (нет)"
    return dedent(
        f"""\
        Человек: {person.name}, дата рождения {person.birth_date.isoformat()}
        {f"в {person.birth_time} " if person.birth_time else ""}в {person.birth_place}.
        {gender_line}{angles}
        Планеты и точки карты:
        {_points_json(prompt_input)}

        natal_aspects (индекс [i] = порядок aspect_interpretations[i]):
        {_indexed_aspects_json(prompt_input)}

        Акценты карты (предвычислены, опирайся на них при расстановке весов):
        {features}

        Баланс стихий (взвешенный): {json.dumps(prompt_input.element_balance, ensure_ascii=False)}
        Баланс крестов: {json.dumps(prompt_input.modality_balance, ensure_ascii=False)}

        accuracy_note: {build_accuracy_note(prompt_input)}
        """
    ).strip()


def build_skeleton_user_message(prompt_input: NatalPromptInput) -> str:
    return dedent(
        f"""\
        Шаг 1: составь скелет разбора натальной карты.

        {_shared_context_block(prompt_input)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(NatalNarrativeSkeleton)}

        Пример корректного ответа:
        {_example_json(_SKELETON_EXAMPLE)}

        Правила:
        1. core_story — 3 абзаца через \\n\\n: как человек звучит → внутренний
           конфликт → суперсила. Каждый абзац опирается на названные факторы.
        2. central_tension выбери из самых весомых противоречий (большая тройка,
           напряжённые аспекты личных планет, конфигурации) — не из фона.
        3. metrics — 4 числа 0.0–1.0 (энергия, эмоции, коммуникация, устойчивость),
           согласованные со стихиями и аспектами: огонь/Марс → энергия,
           вода/Луна → эмоции, воздух/Меркурий → коммуникация,
           земля/Сатурн/фиксированный крест → устойчивость.
        """
    ).strip()


def build_content_user_message(
    prompt_input: NatalPromptInput,
    skeleton: NatalNarrativeSkeleton,
) -> str:
    aspects_count = len(prompt_input.aspects)
    asc_rule = (
        "asc_text — как человека видят со стороны (асцендент)."
        if prompt_input.person.has_time
        else "asc_text верни null — время рождения неизвестно."
    )
    return dedent(
        f"""\
        Шаг 2: полный контент разбора натальной карты.

        {_shared_context_block(prompt_input)}

        narrative_skeleton (шаг 1):
        {skeleton.model_dump_json(indent=2)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(NatalContentRaw)}

        Пример структуры (aspect_interpretations — ровно {aspects_count} шт., здесь сокращён):
        {_example_json(_CONTENT_EXAMPLE)}

        Правила:
        1. aspect_interpretations — ровно {aspects_count} объектов, порядок = индексы
           [0]…[{aspects_count - 1}]. Каждый body: что это даёт в жизни — сцена
           или узнаваемая ситуация, 2–3 предложения.
        2. {asc_rule}
        3. spheres — ровно 3, в порядке: призвание/карьера, отношения,
           ресурсы/деньги. Каждый text называет конкретные факторы карты.
        4. zone_items — 3 списка по 3–5 коротких пунктов, каждый пункт
           начинается с фактора карты («Марс в Овне: …»).
        5. practical_tips — 3–5 действий, каждое начинается с глагола
           и выполнимо за неделю.
        6. core_story — уточни скелет, сохрани 3 абзаца через \\n\\n.
        7. Тексты планет (sun_text и др.) не повторяют друг друга и core_story —
           у каждого своя территория смысла.
        """
    ).strip()


def build_polish_user_message(
    prompt_input: NatalPromptInput,
    content: NatalContentRaw,
) -> str:
    aspects_count = len(prompt_input.aspects)
    return dedent(
        f"""\
        Шаг 3: отредактируй тексты разбора — сделай живее и точнее.

        {_shared_context_block(prompt_input)}

        draft_content:
        {content.model_dump_json(indent=2)}

        ---

        Верни JSON-объект с полями на верхнем уровне (не JSON Schema):

        {_format_model_fields(NatalPolishRaw)}

        Пример корректного ответа (aspect_interpretations — ровно {aspects_count} шт.):
        {_example_json(_POLISH_EXAMPLE)}

        Правила:
        1. Сохрани факты, отсылки к планетам и количество элементов
           (aspect_interpretations: {aspects_count}, spheres: 3).
        2. Вычисти Barnum-фразы: если предложение подходит любому человеку —
           перепиши его через конкретный фактор карты или удали.
        3. Убери повторы между разделами; усиль сцены «когда ты…».
        4. tldr — 2–3 предложения, цепляет с первой строки.
        """
    ).strip()


def parse_natal_skeleton(raw: str) -> tuple[NatalNarrativeSkeleton | None, str | None]:
    return _parse_model(raw, NatalNarrativeSkeleton)


def parse_natal_content(raw: str) -> tuple[NatalContentRaw | None, str | None]:
    return _parse_model(raw, NatalContentRaw)


def parse_natal_polish(raw: str) -> tuple[NatalPolishRaw | None, str | None]:
    return _parse_model(raw, NatalPolishRaw)


def assemble_from_pipeline(
    prompt_input: NatalPromptInput,
    content: NatalContentRaw,
    polish: NatalPolishRaw,
) -> NatalLlmOutput:
    if len(polish.aspect_interpretations) != len(prompt_input.aspects):
        msg = "polish aspect_interpretations length mismatch"
        raise ValueError(msg)
    merged = merge_polish(content, polish)
    return assemble_llm_output(merged, prompt_input)
