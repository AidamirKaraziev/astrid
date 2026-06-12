"""Промпты и постобработка ежедневного прогноза Astrid v2.

Короткий прогноз: 4 предложения + совет, число и цвет дня.
Оптимизирован под gemma4:e2b.
"""

from __future__ import annotations

import json
import re
from datetime import date
from textwrap import dedent
from zoneinfo import ZoneInfo

from astra.astro.schemas import AstroContext, NatalChartData
from astra.users.models import Profile

MIN_SENTENCES = 4
MAX_SENTENCES = 4

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
_NUMBER_VALUE = re.compile(r"(?i)(🔢\s*число\s*дня\s*:?\s*)(\d+)")

_HIEROGLYPH_PATTERN = re.compile(
    r"["
    r"\u3040-\u30ff"
    r"\u3400-\u4dbf"
    r"\u4e00-\u9fff"
    r"\uf900-\ufaff"
    r"\uac00-\ud7a3"
    r"]+",
)


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

    Текст:
    - Ровно {MIN_SENTENCES} предложения, связный рассказ, без подзаголовков.
    - Первое предложение ОБЯЗАТЕЛЬНО начни с имени из данных в именительном падеже: «Марина, сегодня…», «Аид, сегодня…». Не склоняй имя (не «Марине», не «Аиду»).
    - Дальше обращение на «ты»; имя больше не повторяй.
    - Можно назвать планету и аспект, если они есть в transits — но переведи на быт: чувства, разговоры, дела, тело.
    - Не пугай, не обещай событий наверняка.
    - Только данные из сообщения.
    - Запрещено: {_format_forbidden_phrases()}, {_format_cliche_words()}.

    Язык: только русский (кириллица), цифры, пунктуация и эмодзи формата. Без иероглифов.

    Формат ответа (строго):

    ✨ Прогноз дня

    [{MIN_SENTENCES} предложения]

    💡 Совет дня:
    [1 конкретное действие]

    🔢 Число дня:
    [1–99, не повторяй одно и то же число без привязки к дню]

    🎨 Цвет дня:
    [один цвет]
    """,
).strip()


def build_system_prompt() -> str:
    """System prompt: Astrid v2 для gemma4:e2b."""
    return _SYSTEM_PROMPT


def build_user_message(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
) -> str:
    """User prompt: профиль + натал + компактные транзиты."""
    display_name = (profile.display_name or "").strip() or "друг"
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
        """,
    ).strip()


def sanitize_prediction_output(
    raw: str,
    *,
    prediction_date: date | None = None,
    sun_sign: str | None = None,
) -> str:
    """Нормализовать структуру ответа; сохранить разделы и эмодзи."""
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
    text = _strip_hieroglyphs(text)
    text = _rewrite_cliches(text)
    text = _limit_main_body_sentences(text, MAX_SENTENCES)
    text = _fix_biased_day_number(text, prediction_date, sun_sign)
    text = _ensure_forecast_header(text)
    return text


def day_number_for_date(prediction_date: date, sun_sign: str | None = None) -> int:
    """Детерминированное число дня 1–99 по дате и солнечному знаку."""
    sun = (sun_sign or "").strip()
    return (prediction_date.day + prediction_date.month + (ord(sun[:1]) if sun else 0)) % 98 + 1


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


def _ensure_forecast_header(text: str) -> str:
    if "прогноз дня" in text.lower():
        return text
    return f"✨ Прогноз дня\n\n{text}"


def _fix_biased_day_number(
    text: str,
    prediction_date: date | None,
    sun_sign: str | None,
) -> str:
    """Подменить «12» на детерминированное число — типичный bias gemma4:e2b."""
    if prediction_date is None:
        return text

    def replacer(match: re.Match[str]) -> str:
        value = int(match.group(2))
        if value != 12:
            return match.group(0)
        return f"{match.group(1)}{day_number_for_date(prediction_date, sun_sign)}"

    return _NUMBER_VALUE.sub(replacer, text)


def _limit_main_body_sentences(text: str, max_sentences: int) -> str:
    """Ограничить число предложений в блоке «Прогноз дня», футер не трогать."""
    advice_match = _SECTION_ADVICE.search(text)
    if advice_match:
        head = text[: advice_match.start()].rstrip()
        tail = text[advice_match.start() :].lstrip()
        body = _strip_forecast_title(head)
        limited = _limit_sentences(body, max_sentences)
        return f"{limited}\n\n{tail}" if tail else limited
    body = _strip_forecast_title(text)
    return _limit_sentences(body, max_sentences)


def _strip_forecast_title(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    filtered = [
        ln
        for ln in lines
        if ln and not re.match(r"^✨\s*прогноз\s*дня\s*$", ln, flags=re.IGNORECASE)
    ]
    return " ".join(filtered).strip() if filtered else text.strip()


def _limit_sentences(text: str, max_sentences: int) -> str:
    chunks = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks = [c.strip() for c in chunks if c.strip()]
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
