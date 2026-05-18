"""URL и разбор данных Telegram Web App (геолокация на Desktop)."""

import json
from urllib.parse import urlparse

from astra.core.config import Settings


def get_location_webapp_url(settings: Settings) -> str | None:
    """
    Публичный HTTPS-URL страницы геолокации.
    Для локальной разработки укажите WEBAPP_BASE_URL (например ngrok).
    """
    base = (settings.webapp_base_url or "").strip().rstrip("/")
    if not base and settings.telegram_webhook_url:
        parsed = urlparse(settings.telegram_webhook_url)
        if parsed.scheme and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
    if not base and settings.is_development:
        base = "http://127.0.0.1:8000"
    if not base:
        return None
    return f"{base}/telegram/webapp/location"


def parse_webapp_location_payload(data: str) -> tuple[float, float] | None:
    try:
        obj = json.loads(data)
        lat = float(obj["lat"])
        lon = float(obj["lon"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon
