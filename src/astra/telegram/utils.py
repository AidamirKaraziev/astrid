from datetime import date, datetime, time

from aiogram.types import User as TgUser


def parse_birth_date(text: str) -> date | None:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_birth_time(text: str) -> time | None:
    text = text.strip()
    for fmt in ("%H:%M", "%H.%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def extract_referral_code(start_arg: str | None) -> str | None:
    if not start_arg:
        return None
    if start_arg.startswith("ref_"):
        return start_arg[4:]
    return None


def extract_gift_code(start_arg: str | None) -> str | None:
    """Код подарка из `?start=gift_<код>`.

    Подарок несёт и реферальную привязку, поэтому отдельной `ref_`-ссылки
    дарителю слать не нужно: связь ставится по дарителю кода.
    """
    if not start_arg:
        return None
    if start_arg.startswith("gift_"):
        return start_arg[5:]
    return None


def default_display_name(tg_user: TgUser) -> str:
    if tg_user.first_name:
        return tg_user.first_name
    if tg_user.username:
        return tg_user.username
    return "друг"


# Имя человек вписывает сам, а бот подставляет его в сообщения с HTML-разметкой.
# Угловые скобки поэтому вырезаются на входе: экранировать пришлось бы в каждом
# из десятков мест, где имя выводится, и одно забытое сломало бы сообщение.
_NAME_MAX_LENGTH = 64


def clean_display_name(text: str | None) -> str | None:
    """Имя из сообщения человека. None — прислали не имя.

    Длинное обрезаем, а не отвергаем: человек написал «Меня зовут Анна, но
    можно Анечка» — лучше сохранить начало, чем требовать переписать.
    """
    name = (text or "").replace("<", "").replace(">", "").strip()
    if not name or name.startswith("/"):
        return None
    return name[:_NAME_MAX_LENGTH].strip() or None
