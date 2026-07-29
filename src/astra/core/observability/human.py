"""Человекочитаемый вывод логов: одна строка — одно событие, глазами по колонкам.

Зачем свой рендерер, а не JSON: сборщика логов в проекте нет, Sentry берёт
ошибки своим каналом, и единственный читатель stdout — человек в терминале или
в `docker compose logs`. JSON остаётся под флагом LOG_FORMAT=json на случай,
когда появится Loki.

Формат строки:

    08:46:42  warn   telegram.api.failed   user=4819237 product=tarot_wish reason=timeout

Ключи событий оставлены как есть — по ним ищут grep'ом и они же встречаются в
коде. Поля выстроены по важности: сначала кто и что, потом деньги и причина,
и только затем всё остальное. Служебные (correlation_id, service, logger)
уходят в хвост приглушённым цветом или отбрасываются вовсе — иначе они
занимают полстроки и прячут смысл.
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Время показываем в поясе, в котором живёт владелец — так проще сопоставлять
# логи с жалобой «в девять утра не пришёл прогноз».
DISPLAY_TIMEZONE = ZoneInfo("Europe/Moscow")

# Поля, которые важнее прочих: показываем в этом порядке слева направо.
_PRIORITY = (
    "user_id",
    "telegram_id",
    "product_code",
    "action",
    "spread_type",
    "question_key",
    "reading_id",
    "report_id",
    "amount",
    "currency",
    "discount_percent",
    "provider",
    "model",
    "purpose",
    "status",
    "reason",
    "error",
    "error_type",
    "hint",
    "duration_ms",
    "count",
)

# Служебное: в строке не нужно, смысла не добавляет.
_DROP = {"service", "timestamp", "level", "event", "logger", "_record", "_from_structlog"}

# Хвостом и приглушённо — пригождается редко, но иногда спасает.
_TAIL = ("correlation_id", "trace_id", "span_id")

_LEVEL_STYLE = {
    "debug": ("debug", "\033[90m"),
    "info": ("info ", "\033[36m"),
    "warning": ("warn ", "\033[33m"),
    "error": ("ERROR", "\033[31m"),
    "critical": ("CRIT ", "\033[1;31m"),
}

_DIM = "\033[90m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_MAX_VALUE = 70
_EVENT_WIDTH = 30


def _shorten(value: object) -> str:
    """UUID режем до восьми знаков: глазами их всё равно сравнивают по началу."""
    text = str(value)
    if len(text) == 36 and text.count("-") == 4:
        return text[:8]
    if len(text) > _MAX_VALUE:
        return text[: _MAX_VALUE - 1] + "…"
    return text.replace("\n", " ")


def _time(raw: object) -> str:
    """ISO-время из structlog → часы:минуты:секунды в местном поясе."""
    if not isinstance(raw, str):
        return datetime.now(DISPLAY_TIMEZONE).strftime("%H:%M:%S")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:8]
    return moment.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M:%S")


class HumanRenderer:
    """Процессор structlog: словарь события → одна читаемая строка."""

    def __init__(self, colors: bool | None = None) -> None:
        # В терминале — цвет, в `docker compose logs` — обычный текст:
        # там escape-последовательности превратились бы в мусор.
        self.colors = sys.stdout.isatty() if colors is None else colors

    def _paint(self, text: str, color: str) -> str:
        return f"{color}{text}{_RESET}" if self.colors else text

    def __call__(self, logger, name, event_dict: dict) -> str:
        event = str(event_dict.pop("event", ""))
        level = str(event_dict.pop("level", "info")).lower()
        label, color = _LEVEL_STYLE.get(level, ("info ", ""))
        moment = _time(event_dict.get("timestamp"))

        exc = event_dict.pop("exception", None) or event_dict.pop("exc_info", None)
        for key in _DROP:
            event_dict.pop(key, None)

        tail = [(key, event_dict.pop(key)) for key in _TAIL if key in event_dict]

        ordered: list[tuple[str, object]] = [
            (key, event_dict.pop(key)) for key in _PRIORITY if key in event_dict
        ]
        ordered += sorted(event_dict.items())

        fields = " ".join(f"{key}={_shorten(value)}" for key, value in ordered)
        event_column = event.ljust(_EVENT_WIDTH) if len(event) < _EVENT_WIDTH else event

        line = (
            f"{self._paint(moment, _DIM)}  "
            f"{self._paint(label, color)}  "
            f"{self._paint(event_column, _BOLD if level in {'error', 'critical'} else '')}"
        )
        if fields:
            line += f"  {fields}"
        if tail:
            suffix = " ".join(f"{key}={_shorten(value)}" for key, value in tail)
            line += f"  {self._paint(suffix, _DIM)}"
        if exc:
            line += f"\n{exc}" if isinstance(exc, str) else ""
        return line
