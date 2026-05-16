from astra.core.cities import resolve_timezone
from astra.telegram.utils import extract_referral_code, parse_birth_date, parse_birth_time


def test_parse_birth_date() -> None:
    assert parse_birth_date("15.03.1990") == __import__("datetime").date(1990, 3, 15)
    assert parse_birth_date("invalid") is None


def test_parse_birth_time() -> None:
    assert parse_birth_time("14:30").hour == 14
    assert parse_birth_time("bad") is None


def test_extract_referral_code() -> None:
    assert extract_referral_code("ref_abc123") == "abc123"
    assert extract_referral_code(None) is None


def test_resolve_timezone() -> None:
    assert resolve_timezone("Москва") == "Europe/Moscow"
    assert resolve_timezone("Неизвестный") == "Europe/Moscow"
