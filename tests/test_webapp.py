from astra.core.config import Settings
from astra.telegram.webapp import get_location_webapp_url, parse_webapp_location_payload


def test_parse_webapp_location_payload_ok() -> None:
    assert parse_webapp_location_payload('{"lat": 55.75, "lon": 37.62}') == (55.75, 37.62)


def test_parse_webapp_location_payload_invalid() -> None:
    assert parse_webapp_location_payload("not-json") is None
    assert parse_webapp_location_payload('{"lat": 999, "lon": 0}') is None


def test_get_location_webapp_url_from_base() -> None:
    settings = Settings(webapp_base_url="https://astra.example.com")
    assert get_location_webapp_url(settings) == "https://astra.example.com/telegram/webapp/location"


def test_get_location_webapp_url_dev_fallback() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        webapp_base_url="",
        telegram_webhook_url=None,
    )
    assert get_location_webapp_url(settings) == "http://127.0.0.1:8000/telegram/webapp/location"
