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


def default_display_name(tg_user: TgUser) -> str:
    if tg_user.first_name:
        return tg_user.first_name
    if tg_user.username:
        return tg_user.username
    return "друг"
