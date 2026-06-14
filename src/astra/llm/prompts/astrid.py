"""Промпты и постобработка ежедневного прогноза Astrid v3.

Формат: вопрос дня + 4 предложения + совет. Оптимизирован под gemma4:e2b.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from textwrap import dedent
from uuid import UUID
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData
from astra.users.models import Profile

MIN_SENTENCES = 4
MAX_SENTENCES = 4
MIN_BODY_SENTENCES = 3
MAX_BODY_SENTENCES = 6
MIN_BODY_WORDS = 15
MAX_BODY_WORDS = 180
MIN_QUESTION_LEN = 15
MAX_QUESTION_LEN = 65

_FORBIDDEN_LEAK_PATTERNS = (
    r"^\s*(анализ|шаг\s*\d|внутренне|json)\s*[:—\-]",
    r"^\s*```",
)

_GENERIC_PHRASES = (
    "вас ждут перемены",
    "будьте внимательны",
    "возможны интересные события",
    "общая энергия дня",
    "благоприятный день для",
    "звёзды советуют",
    "космос подсказывает",
    "внутренние процессы",
    "прекрасное время",
)

_CLICHE_WORDS = (
    "ритм",
    "гармония",
    "трансформация",
    "вибрации",
    "энергетика",
)

_CLICHE_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"внутренн\w*\s+процесс\w*", re.IGNORECASE), "фокус дня"),
    (re.compile(r"прекрасн\w*\s+время", re.IGNORECASE), "хороший момент"),
    (re.compile(r"солнечн\w*\s+ритм\w*", re.IGNORECASE), "солнечный знак"),
    (re.compile(r"ритм\s+дня", re.IGNORECASE), "настроение дня"),
    (re.compile(r"пойма\w*\s+ритм", re.IGNORECASE), "найдёшь свой темп"),
    (re.compile(r"\bритм\w*\b", re.IGNORECASE), "темп"),
    (re.compile(r"\bгармон\w*\b", re.IGNORECASE), "спокойствие"),
)

_SECTION_ADVICE = re.compile(r"(?i)💡\s*совет\s*дня\s*:?")
_SECTION_NUMBER = re.compile(r"(?i)🔢\s*число\s*дня\s*:?")
_SECTION_COLOR = re.compile(r"(?i)🎨\s*цвет\s*дня\s*:?")
_FORECAST_TITLE = re.compile(r"^✨\s*прогноз\s*дня\s*$", re.IGNORECASE)

_HIEROGLYPH_PATTERN = re.compile(
    r"["
    r"\u3040-\u30ff"
    r"\u3400-\u4dbf"
    r"\u4e00-\u9fff"
    r"\uf900-\ufaff"
    r"\uac00-\ud7a3"
    r"]+",
)


@dataclass(frozen=True, slots=True)
class QuestionArchetype:
    """Семейство вопроса дня: тема + пример тона (не копировать дословно)."""

    id: str
    theme: str
    example: str


QUESTION_ARCHETYPES: tuple[QuestionArchetype, ...] = (
    QuestionArchetype(
        id="postpone",
        theme="что откладываешь, приоритеты vs прокрастинация",
        example="Что ты откладываешь дольше, чем нужно?",
    ),
    QuestionArchetype(
        id="right_or_close",
        theme="правота vs близость в разговорах",
        example="Что важнее — быть правым или быть близким?",
    ),
    QuestionArchetype(
        id="urgent_vs_important",
        theme="важное vs срочное, выбор приоритетов",
        example="Где ты меняешь важное на срочное?",
    ),
    QuestionArchetype(
        id="listen_not_convince",
        theme="слушать vs переубеждать в диалогах",
        example="Кого сегодня стоит услышать, а не переубедить?",
    ),
    QuestionArchetype(
        id="let_go_new",
        theme="отпустить старое ради нового, пересмотр намерений",
        example="Что ты отпускаешь, чтобы освободить место для нового?",
    ),
    QuestionArchetype(
        id="avoided_truth",
        theme="правда, которую избегаешь в близком общении",
        example="Какую правду ты избегаешь в разговоре с близкими?",
    ),
)


def pick_question_archetype(user_id: UUID, prediction_date: date) -> QuestionArchetype:
    """Детерминированный архетип вопроса: один user + день → один тип."""
    key = f"{user_id}:{prediction_date.isoformat()}".encode()
    digest = hashlib.sha256(key).digest()
    index = int.from_bytes(digest[:4], "big") % len(QUESTION_ARCHETYPES)
    return QUESTION_ARCHETYPES[index]


def format_archetype_hint(archetype: QuestionArchetype) -> str:
    """Блок подсказки для user message."""
    return dedent(
        f"""
        Тип вопроса дня: {archetype.theme}
        Напиши свой вопрос в этом духе — не копируй дословно.
        Пример тона: «{archetype.example}»
        Вопрос должен намекать на суть дня по транзитам, но не пересказывать прогноз.
        """,
    ).strip()


def _format_forbidden_phrases() -> str:
    return ", ".join(f"«{p}»" for p in _GENERIC_PHRASES)


def _format_cliche_words() -> str:
    return ", ".join(f"«{w}»" for w in _CLICHE_WORDS)


_SYSTEM_PROMPT = dedent(
    f"""
    Ты — Astrid, астролог в Telegram-боте Astra.

    Задача: показать, что сегодня важно именно для этого человека — не общий гороскоп.

    Как думать (не выводи):
    1. Коротко опирайся на натал: Солнце = воля/эго, Луна = эмоции (если есть), ASC = как человек входит в день (если есть).
    2. Транзиты с меньшим orb — что сегодня задевает эти точки натала.
    3. Сформулируй главный инсайт дня простым языком.
    4. Сначала определи суть дня (не выводи), затем напиши вопрос дня как намёк на неё.

    Вопрос дня:
    - Одна строка, {MIN_QUESTION_LEN}–{MAX_QUESTION_LEN} символов, обязательно с «?» в конце.
    - Таинственный, личный — как шёпот, не инструкция.
    - Намекает на суть дня: человек чувствует тему, но не знает ответа.
    - Не называй планеты. Не пересказывай прогноз. Без кавычек, скобок, эмодзи.
    - Не используй слова «сегодня», «фокус», «задачи», «вопрос».

    Прогноз:
    - Около {MIN_SENTENCES} предложений (обычно {MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES}), связный рассказ, без подзаголовков.
    - Первое предложение ОБЯЗАТЕЛЬНО начни с имени из данных в именительном падеже: «Марина, сегодня…», «Аид, сегодня…». Не склоняй имя (не «Марине», не «Аиду»).
    - Дальше обращение на «ты»; имя больше не повторяй.
    - Можно назвать планету и аспект, если они есть в transits — но переведи на быт: чувства, разговоры, дела, тело.
    - Не пугай, не обещай событий наверняка.
    - Только данные из сообщения.
    - Запрещено: {_format_forbidden_phrases()}, {_format_cliche_words()}.

    Совет:
    - Ровно одно предложение, без заголовка и эмодзи.
    - Конкретное действие на сегодня.

    Язык: только русский (кириллица). Без иероглифов.

    Формат ответа (строго, три блока через пустую строку):

    [вопрос дня — одна строка]

    [{MIN_SENTENCES} предложения прогноза, допустимо {MIN_BODY_SENTENCES}–{MAX_BODY_SENTENCES}]

    [1 предложение совета]
    """,
).strip()


def build_system_prompt() -> str:
    """System prompt: Astrid v3 для gemma4:e2b."""
    return _SYSTEM_PROMPT


def build_user_message(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
    *,
    archetype: QuestionArchetype | None = None,
) -> str:
    """User prompt: профиль + натал + транзиты + подсказка архетипа вопроса."""
    display_name = (profile.display_name or "").strip() or "друг"
    if archetype is None:
        archetype = pick_question_archetype(profile.user_id, ctx.date)

    transits = [
        {
            "transit": t.transit_planet,
            "aspect": t.aspect,
            "natal": t.natal_planet,
            "orb": t.orb_deg,
            "theme": t.theme,
        }
        for t in ctx.transits
    ]
    transits_json = json.dumps(transits, ensure_ascii=False, indent=2)
    archetype_hint = format_archetype_hint(archetype)
    return dedent(
        f"""
        Составь персональный прогноз на день для этого человека.

        Имя: {display_name}
        Дата прогноза: {ctx.date.isoformat()}
        Дата рождения: {_format_birth_date(profile)}
        Время рождения: {_format_birth_time(profile)}
        Место рождения: {_format_birth_place(profile)}
        Натал: Солнце {chart.sun_sign}, Луна {_format_moon(chart)}, ASC {_format_asc(chart)}
        Точность профиля: {chart.accuracy_tier}%

        Транзиты сегодня (JSON, меньший orb — сильнее влияние):
        {transits_json}

        {archetype_hint}
        """,
    ).strip()


def sanitize_prediction_output(raw: str) -> str:
    """Нормализовать v3-ответ: вопрос + прогноз + совет."""
    text = _pre_clean_raw(raw)
    if not text:
        return text

    question, body, advice = _parse_raw_blocks(text)
    question = _normalize_question(question)
    body = _normalize_body(body)
    advice = _normalize_advice(advice)

    if not question or not body or not advice:
        return ""

    return _assemble_blocks(question, body, advice)


def validate_prediction_output(text: str, display_name: str) -> str | None:
    """Проверить v3-прогноз; вернуть reason для retry или None если ок."""
    cleaned = text.strip()
    if not cleaned:
        return "sanitize_empty"

    if _contains_forbidden_content(cleaned):
        return "forbidden_content"

    if _LEGACY_MARKERS.search(cleaned):
        return "legacy_format"

    blocks = _split_assembled_blocks(cleaned)
    if blocks is None:
        return "invalid_structure"

    question, body, advice = blocks

    if not question.endswith("?"):
        return "invalid_question"
    if not (MIN_QUESTION_LEN <= len(question) <= MAX_QUESTION_LEN):
        return "question_length"

    if not _body_starts_with_name(body, display_name):
        return "missing_name"

    body_sentences = _split_sentences(body)
    if len(body_sentences) < 2:
        return "body_too_short"
    if len(body_sentences) > MAX_BODY_SENTENCES + 1:
        return "body_too_long"

    body_words = _count_words(body)
    if body_words < MIN_BODY_WORDS or body_words > MAX_BODY_WORDS:
        return "body_word_count"

    advice_sentences = _split_sentences(advice)
    if len(advice_sentences) != 1 or not advice.strip():
        return "invalid_advice"

    return None


def _pre_clean_raw(raw: str) -> str:
    text = raw.strip()
    if not text:
        return text

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'", "«", "»"}:
        text = text[1:-1].strip()

    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()

    for pattern in _FORBIDDEN_LEAK_PATTERNS:
        if re.match(pattern, text, flags=re.IGNORECASE):
            text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _strip_hieroglyphs(text)


def _parse_raw_blocks(text: str) -> tuple[str, str, str]:
    text = _strip_legacy_sections(text)
    blocks = _split_paragraphs(text)

    if not blocks:
        return "", "", ""

    if len(blocks) >= 3:
        question = blocks[0]
        body = blocks[1]
        advice = blocks[2] if len(blocks) == 3 else " ".join(blocks[2:])
        return question, body, advice

    if len(blocks) == 2:
        first, second = blocks
        if _looks_like_question(first):
            return first, second, ""
        return "", first, second

    only = blocks[0]
    if _looks_like_question(only):
        return only, "", ""
    return "", only, ""


def _strip_legacy_sections(text: str) -> str:
    """Убрать v2-секции; сохранить текст совета без заголовка."""
    if _SECTION_ADVICE.search(text):
        head, tail = _SECTION_ADVICE.split(text, maxsplit=1)
        advice = tail.strip()
        advice = _SECTION_NUMBER.split(advice, maxsplit=1)[0].strip()
        advice = _SECTION_COLOR.split(advice, maxsplit=1)[0].strip()
        head = _strip_forecast_title(head.strip())
        if advice:
            return f"{head}\n\n{advice}".strip()
        return head

    without_footer = _SECTION_NUMBER.split(text, maxsplit=1)[0]
    without_footer = _SECTION_COLOR.split(without_footer, maxsplit=1)[0]
    return _strip_forecast_title(without_footer.strip())


def _strip_forecast_title(text: str) -> str:
    paragraphs = re.split(r"\n{2,}", text)
    cleaned: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        lines = [line for line in lines if not _FORECAST_TITLE.match(line)]
        if lines:
            cleaned.append(" ".join(lines))
    return "\n\n".join(cleaned)


def _split_paragraphs(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    return [block for block in blocks if not _FORECAST_TITLE.match(block)]


def _looks_like_question(text: str) -> bool:
    line = _first_line(text)
    return "?" in line and len(line) <= MAX_QUESTION_LEN + 15


def _normalize_question(text: str) -> str:
    question = _first_line(text)
    question = question.strip().strip("[]«»\"'")
    question = re.sub(r"\s+", " ", question).strip()
    if question and not question.endswith("?"):
        question = question.rstrip(".!…") + "?"
    if len(question) > MAX_QUESTION_LEN:
        question = _truncate_question(question)
    return question


def _normalize_body(text: str) -> str:
    body = re.sub(r"\s+", " ", text.strip())
    body = _rewrite_cliches(body)
    body = _limit_sentences(body, MAX_BODY_SENTENCES)
    return body.strip()


def _normalize_advice(text: str) -> str:
    advice = re.sub(r"\s+", " ", text.strip())
    advice = _rewrite_cliches(advice)
    sentences = _split_sentences(advice)
    if not sentences:
        return ""
    return _ensure_terminal_punctuation(sentences[0])


def _assemble_blocks(question: str, body: str, advice: str) -> str:
    return f"{question}\n\n{body}\n\n{advice}"


def _split_assembled_blocks(text: str) -> tuple[str, str, str] | None:
    parts = _split_paragraphs(text)
    if len(parts) < 3:
        return None
    question = parts[0]
    body = parts[1]
    advice = parts[2] if len(parts) == 3 else " ".join(parts[2:])
    return question, body, advice


def _body_starts_with_name(body: str, display_name: str) -> bool:
    name = display_name.strip()
    if not name:
        return True
    first_sentence = _split_sentences(body)[0] if body else ""
    return first_sentence.startswith(f"{name},") or first_sentence.startswith(f"{name} ")


def _contains_forbidden_content(text: str) -> bool:
    lowered = text.lower()
    if _HIEROGLYPH_PATTERN.search(text):
        return True
    return any(phrase in lowered for phrase in _GENERIC_PHRASES)


_LEGACY_MARKERS = re.compile(r"✨|💡|🔢|🎨")


def _truncate_question(question: str) -> str:
    if len(question) <= MAX_QUESTION_LEN:
        return question
    truncated = question[: MAX_QUESTION_LEN + 1]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    if not truncated.endswith("?"):
        truncated = truncated.rstrip(".!…, ") + "?"
    return truncated[:MAX_QUESTION_LEN].rstrip()


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _count_words(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _format_birth_date(profile: Profile) -> str:
    return profile.birth_date.isoformat()


def _format_birth_time(profile: Profile) -> str:
    if profile.birth_time is None:
        return "не указано"
    tz = ZoneInfo(profile.timezone)
    local = profile.birth_time
    if local.tzinfo is None:
        local = local.replace(tzinfo=tz)
    else:
        local = local.astimezone(tz)
    return local.strftime("%H:%M")


def _format_birth_place(profile: Profile) -> str:
    return (profile.birth_place or profile.city or "не указано").strip()


def _format_moon(chart: NatalChartData) -> str:
    return chart.moon_sign or "не рассчитана"


def _format_asc(chart: NatalChartData) -> str:
    return chart.asc_sign or "не рассчитан"


def _rewrite_cliches(text: str) -> str:
    """Подменить типичные клише, если модель всё же их вставила."""
    for pattern, replacement in _CLICHE_REWRITES:
        text = pattern.sub(replacement, text)
    return text


def _strip_hieroglyphs(text: str) -> str:
    return _HIEROGLYPH_PATTERN.sub("", text)


def _limit_sentences(text: str, max_sentences: int) -> str:
    chunks = _split_sentences(text)
    if len(chunks) <= max_sentences:
        return _ensure_terminal_punctuation(text)
    return _ensure_terminal_punctuation(" ".join(chunks[:max_sentences]))


def _ensure_terminal_punctuation(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text[-1] not in ".!?…":
        return text + "."
    return text
