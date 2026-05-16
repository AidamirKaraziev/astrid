"""City name → IANA timezone mapping for RU MVP."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Normalized lowercase keys
CITY_TIMEZONES: dict[str, str] = {
    "москва": "Europe/Moscow",
    "moscow": "Europe/Moscow",
    "санкт-петербург": "Europe/Moscow",
    "спб": "Europe/Moscow",
    "питер": "Europe/Moscow",
    "новосибирск": "Asia/Novosibirsk",
    "екатеринбург": "Asia/Yekaterinburg",
    "казань": "Europe/Moscow",
    "нижний новгород": "Europe/Moscow",
    "челябинск": "Asia/Yekaterinburg",
    "самара": "Europe/Samara",
    "омск": "Asia/Omsk",
    "ростов-на-дону": "Europe/Moscow",
    "уфа": "Asia/Yekaterinburg",
    "красноярск": "Asia/Krasnoyarsk",
    "воронеж": "Europe/Moscow",
    "пермь": "Asia/Yekaterinburg",
    "волгоград": "Europe/Volgograd",
    "краснодар": "Europe/Moscow",
    "сочи": "Europe/Moscow",
    "владивосток": "Asia/Vladivostok",
    "хабаровск": "Asia/Vladivostok",
    "иркутск": "Asia/Irkutsk",
    "тюмень": "Asia/Yekaterinburg",
    "тольятти": "Europe/Samara",
    "барнаул": "Asia/Barnaul",
    "ижевск": "Europe/Samara",
    "махачкала": "Europe/Moscow",
    "ульяновск": "Europe/Ulyanovsk",
    "ярославль": "Europe/Moscow",
    "севастополь": "Europe/Moscow",
    "симферополь": "Europe/Moscow",
}

DEFAULT_TIMEZONE = "Europe/Moscow"


def normalize_city(city: str) -> str:
    return " ".join(city.strip().lower().split())


def resolve_timezone(city: str) -> str:
    key = normalize_city(city)
    return CITY_TIMEZONES.get(key, DEFAULT_TIMEZONE)


def validate_timezone(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except ZoneInfoNotFoundError:
        return False
