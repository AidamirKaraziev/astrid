"""Одноразовый dev-скрипт: скачать 78 сканов Райдер-Уэйт с Wikimedia Commons.

Лицензия: колода Райдер-Уэйт опубликована в 1909, художница Pamela Colman Smith
умерла в 1951 — с 2022 года изображения в public domain по всему миру.
Источник: https://commons.wikimedia.org/wiki/Category:Rider%E2%80%93Waite_tarot_deck
(файлы RWS_Tarot_*.jpg, Wands*.jpg, Cups*.jpg, Swords*.jpg, Pents*.jpg).

Запуск (Pillow и httpx не в зависимостях проекта — подключаются на лету):
    uv run --with pillow --with httpx python scripts/fetch_tarot_images.py

Результат: src/astra/telegram/static/tarot/{card_id}.jpg — ~400px по ширине,
JPEG quality 82, суммарно ~5 МБ. Файлы коммитятся в репозиторий.
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent.parent / "src/astra/telegram/static/tarot"
FILEPATH_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=400"
HEADERS = {"User-Agent": "AstraTarotFetcher/1.0 (dev one-off; contact: repo owner)"}

_MAJOR_NAMES = {
    0: "RWS_Tarot_00_Fool.jpg",
    1: "RWS_Tarot_01_Magician.jpg",
    2: "RWS_Tarot_02_High_Priestess.jpg",
    3: "RWS_Tarot_03_Empress.jpg",
    4: "RWS_Tarot_04_Emperor.jpg",
    5: "RWS_Tarot_05_Hierophant.jpg",
    6: "RWS_Tarot_06_Lovers.jpg",
    7: "RWS_Tarot_07_Chariot.jpg",
    8: "RWS_Tarot_08_Strength.jpg",
    9: "RWS_Tarot_09_Hermit.jpg",
    10: "RWS_Tarot_10_Wheel_of_Fortune.jpg",
    11: "RWS_Tarot_11_Justice.jpg",
    12: "RWS_Tarot_12_Hanged_Man.jpg",
    13: "RWS_Tarot_13_Death.jpg",
    14: "RWS_Tarot_14_Temperance.jpg",
    15: "RWS_Tarot_15_Devil.jpg",
    16: "RWS_Tarot_16_Tower.jpg",
    17: "RWS_Tarot_17_Star.jpg",
    18: "RWS_Tarot_18_Moon.jpg",
    19: "RWS_Tarot_19_Sun.jpg",
    20: "RWS_Tarot_20_Judgement.jpg",
    21: "RWS_Tarot_21_World.jpg",
}

_SUIT_COMMONS_PREFIX = {
    "wands": "Wands",
    "cups": "Cups",
    "swords": "Swords",
    "pentacles": "Pents",
}
_COURT_NUMBERS = {"page": 11, "knight": 12, "queen": 13, "king": 14}


def commons_name(card_id: str) -> str:
    kind, _, tail = card_id.partition("_")
    if kind == "major":
        return _MAJOR_NAMES[int(tail)]
    number = _COURT_NUMBERS.get(tail) or int(tail)
    return f"{_SUIT_COMMONS_PREFIX[kind]}{number:02d}.jpg"


def normalize_jpeg(raw: bytes) -> bytes:
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    if image.width > 400:
        ratio = 400 / image.width
        image = image.resize((400, round(image.height * ratio)), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from astra.tarot.deck import DECK

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as client:
        for card in DECK:
            target = OUT_DIR / f"{card.id}.jpg"
            if target.exists():
                print(f"skip  {card.id} (уже скачано)")
                continue
            url = FILEPATH_URL.format(name=commons_name(card.id))
            response = client.get(url)
            for attempt in range(4):  # вежливый бэкофф на 429 от Commons
                if response.status_code != 429:
                    break
                time.sleep(float(response.headers.get("Retry-After", 5 * (attempt + 1))))
                response = client.get(url)
            if response.status_code != 200 or not response.content:
                failures.append(f"{card.id} ← {url} → HTTP {response.status_code}")
                continue
            time.sleep(0.5)  # не душить Commons
            target.write_bytes(normalize_jpeg(response.content))
            print(f"ok    {card.id} ({target.stat().st_size // 1024} КБ)")
    if failures:
        print("\nНЕ СКАЧАЛИСЬ:\n" + "\n".join(failures))
        return 1
    total_kb = sum(f.stat().st_size for f in OUT_DIR.glob("*.jpg")) // 1024
    print(f"\nГотово: {len(list(OUT_DIR.glob('*.jpg')))} файлов, {total_kb} КБ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
