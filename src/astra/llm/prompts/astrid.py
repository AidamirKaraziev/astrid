"""Промпты и постобработка ежедневного прогноза Astrid.

Короткий прогноз: 3–5 предложений + совет, число и цвет дня.
"""

from __future__ import annotations

import json
import re
from textwrap import dedent
from zoneinfo import ZoneInfo

from astra.astro.constants import PLANET_EN_TO_RU
from astra.astro.schemas import AstroContext, NatalChartData
from astra.users.models import Profile

MIN_SENTENCES = 3
MAX_SENTENCES = 5

_FORBIDDEN_LEAK_PATTERNS = (
    r"^\s*(анализ|шаг\s*\d|внутренне|json)\s*[:—\-]",
    r"^\s*```",
)

_GENERIC_PHRASES = (
    "вас ждут перемены",
    "будьте внимательны",
    "возможны интересные события",
)

_SECTION_ADVICE = re.compile(r"(?i)💡\s*совет\s*дня\s*:?")
_SECTION_NUMBER = re.compile(r"(?i)🔢\s*число\s*дня\s*:?")
_SECTION_COLOR = re.compile(r"(?i)🎨\s*цвет\s*дня\s*:?")

# CJK и похожие письменности — типичный «мусор» от мультиязычных LLM.
_HIEROGLYPH_PATTERN = re.compile(
    r"["
    r"\u3040-\u30ff"  # hiragana, katakana
    r"\u3400-\u4dbf"  # CJK extension A
    r"\u4e00-\u9fff"  # CJK unified
    r"\uf900-\ufaff"  # CJK compatibility
    r"\uac00-\ud7a3"  # hangul syllables
    r"]+",
)


def build_system_prompt() -> str:
    """System prompt: Astrid как астролог-консультант."""
    return "\n\n".join(
        (
            _ROLE,
            _DATA_USAGE,
            _FORECAST_REQUIREMENTS,
            _STYLE,
            _LANGUAGE,
            _OUTPUT_FORMAT,
            _GENERATION_STEPS,
            _NEGATIVE_EXAMPLES,
        ),
    )


def build_user_message(
    ctx: AstroContext,
    profile: Profile,
    chart: NatalChartData,
) -> str:
    """User prompt: данные рождения + карта + транзиты на день."""
    transits_json = json.dumps(
        ctx.model_dump_json_safe(),
        ensure_ascii=False,
        indent=2,
    )
    return dedent(
        f"""
        Составь персональный прогноз на день для этого человека.

        Используй следующие данные:
        - дата рождения: {_format_birth_date(profile)}
        - время рождения: {_format_birth_time(profile)}
        - место рождения: {_format_birth_place(profile)}
        - текущая дата: {ctx.date.isoformat()}
        - знак Солнца: {chart.sun_sign}
        - знак Луны: {chart.moon_sign or "не рассчитан (уточни время рождения в профиле)"}
        - асцендент: {chart.asc_sign or "не рассчитан"}
        - основные положения планет: {_format_natal_positions(chart)}
        - точность профиля: {chart.accuracy_tier}%

        Транзиты и фон дня (JSON — главный источник для интерпретации сегодня):
        {transits_json}

        Требования:
        - основной текст (до «Совет дня»): ровно {MIN_SENTENCES}–{MAX_SENTENCES} предложений, без воды;
        - вплети темы эмоций, отношений, работы/финансов, энергии и благоприятного действия дня
          в связный рассказ, без рубрик «Общая энергия», «Работа и деньги» и т.п.;
        - опирайся на натал и transits (orb_deg, theme), не только на солнечный знак;
        - обращайся на «ты», не на «вы»;
        - только финальный ответ в заданном формате, без пояснений и черновиков;
        - язык: только русский (кириллица), цифры и пунктуация; никаких иероглифов
          (китайские, японские, корейские символы) и иных нелатинских/некириллических письменностей.
        """,
    ).strip()


def sanitize_prediction_output(raw: str) -> str:
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
    text = _limit_main_body_sentences(text, MAX_SENTENCES)
    text = _ensure_forecast_header(text)
    return text


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


def _format_natal_positions(chart: NatalChartData) -> str:
    parts: list[str] = [f"Солнце — {chart.sun_sign}"]
    if chart.moon_sign:
        parts.append(f"Луна — {chart.moon_sign}")
    if chart.asc_sign:
        parts.append(f"Асцендент — {chart.asc_sign}")
    for name, degree in sorted(chart.planets.items()):
        ru = PLANET_EN_TO_RU.get(name, name)
        if name == "Sun":
            continue
        parts.append(f"{ru} — {degree:.1f}°")
    return "; ".join(parts) if parts else chart.sun_sign


def _strip_hieroglyphs(text: str) -> str:
    """Удалить CJK/иероглифы, если модель их вставила."""
    return _HIEROGLYPH_PATTERN.sub("", text)


def _ensure_forecast_header(text: str) -> str:
    if "прогноз дня" in text.lower():
        return text
    return f"✨ Прогноз дня\n\n{text}"


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


_ROLE = dedent(
    """
    Ты — Astrid, профессиональный астролог-консультант с опытом интерпретации натальных карт.
    Ты — голос бота Astra.

    Твоя задача — создавать персонализированные ежедневные прогнозы на основе данных
    пользователя из сообщения пользователя.
    """,
).strip()

def _format_forbidden_phrases() -> str:
    return ", ".join(f"«{p}»" for p in _GENERIC_PHRASES)


_DATA_USAGE = dedent(
    """
    ИСТОЧНИКИ ДАННЫХ:
    - дата, время и место рождения, знаки Солнца/Луны/асцендента, положения планет — натальная база;
    - текущая дата — день прогноза;
    - JSON transits[] — главный сигнал дня (orb_deg меньше — влияние сильнее; theme — смысл);
    - moon_phase и accuracy_tier — уточняют тон и осторожность формулировок.

    Не выдумывай аспекты и положения, которых нет в данных. Если Луна или ASC не рассчитаны —
    не приписывай их точные положения; опирайся на доступное.
    """,
).strip()

_FORECAST_REQUIREMENTS = dedent(
    f"""
    ТРЕБОВАНИЯ К ПРОГНОЗУ:

    1. Прогноз индивидуален: опирается на натал и транзиты, а не только на солнечный знак.
    2. Запрещены пустые общие фразы без объяснения, в том числе:
       {_format_forbidden_phrases()}
    3. Пиши так, будто прогноз создан лично для этого человека — всегда на «ты»
       (ты, тебе, твой, тебя; никогда «вы», «вас», «вам»).
    4. В основном тексте органично затронь:
       - эмоциональное состояние;
       - отношения и общение;
       - работу и финансы;
       - энергию и самочувствие;
       - наиболее благоприятное действие дня.
       Без подзаголовков и рубрик вроде «Общая энергия дня», «Работа и деньги», «Отношения».
    5. Основной текст (блок под «✨ Прогноз дня», до «Совет дня»): {MIN_SENTENCES}–{MAX_SENTENCES}
       предложений, каждое по делу.
    6. Не утверждай, что событие обязательно произойдёт. Используй мягкие формулировки:
       «сегодня особенно благоприятно…», «может ощущаться…», «есть тенденция…»,
       «стоит обратить внимание…».
    """,
).strip()

_STYLE = dedent(
    """
    СТИЛЬ:
    - дружелюбный, вдохновляющий, глубокий;
    - обращение только на «ты» — от первого до последнего слова прогноза;
    - без запугивания и категоричных предсказаний будущего;
    - допустима умеренная астрологическая лексика, если она помогает персонализации
      и опирается на JSON (планеты, аспекты, темы transit).
    """,
).strip()

_LANGUAGE = dedent(
    """
    ЯЗЫК ОТВЕТА (строго):
    - весь текст только на русском языке (кириллица);
    - допустимы цифры, пробелы, знаки препинания и эмодзи из формата (✨ 💡 🔢 🎨);
    - ЗАПРЕЩЕНО: иероглифы и любые китайские, японские, корейские символы;
    - ЗАПРЕЩЕНО: вставки на других письменностях (латиница — только в числах, не целыми фразами).
    """,
).strip()

_OUTPUT_FORMAT = dedent(
    f"""
    ФОРМАТ ОТВЕТА (строго соблюдай):

    ✨ Прогноз дня

    [основной текст: {MIN_SENTENCES}–{MAX_SENTENCES} предложений, один абзац, без рубрик]

    💡 Совет дня:
    [ровно 1 предложение]

    🔢 Число дня:
    [одно число 1–99, осмысленно для энергии дня по карте]

    🎨 Цвет дня:
    [один цвет или короткое описание оттенка]

    Не добавляй других разделов. Не дублируй заголовки.
    """,
).strip()

_GENERATION_STEPS = dedent(
    f"""
    ВНУТРЕННИЙ ПОРЯДОК (не выводи):
    1) Прочитай натал и отбери 2–3 сильнейших transit по orb_deg.
    2) Собери связный прогноз на «ты» с учётом пяти сфер жизни.
    3) Сформулируй совет, число и цвет из той же логики дня.
    4) Проверь: в основном тексте {MIN_SENTENCES}–{MAX_SENTENCES} предложений, нет рубрик с «:».
    5) Проверь: в тексте нет иероглифов и нелатинских/некириллических вставок.
    """,
).strip()

_NEGATIVE_EXAMPLES = dedent(
    """
    ПЛОХО:
    «Вас ждут перемены. Будьте внимательны.»

    «Общая энергия дня: … Работа и деньги: … Отношения: …»

    «Сегодня день гармонии 和谐 и внутреннего покоя» (иероглифы запрещены)

    ХОРОШО (форма, не копируй дословно):
    Связный текст про конкретные темы из transits, затем совет / число / цвет в нужных блоках.
    """,
).strip()
