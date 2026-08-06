"""Названия стран и регионов по-русски.

Справочник перестал быть российским: теперь пятнадцать постсоветских стран,
и у каждой свои области, вилайеты и уезды. Русские названия регионов берутся
из того же источника официальных имён, что и города, — по идентификатору
региона из `admin1CodesASCII.txt`.

Для России остаётся выверенный вручную список (`ru_admin1`): в нём «Ханты-
Мансийский автономный округ — Югра» и прочие полные официальные формы,
которые в GeoNames записаны короче. Он имеет приоритет — менять то, что уже
показано людям в профилях, ради единообразия незачем.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Пятнадцать постсоветских стран. Порядок не важен, важен состав: за его
# пределами мест мы не импортируем.
COUNTRY_NAMES_RU: dict[str, str] = {
    "RU": "Россия",
    "UA": "Украина",
    "BY": "Беларусь",
    "KZ": "Казахстан",
    "UZ": "Узбекистан",
    "KG": "Киргизия",
    "TJ": "Таджикистан",
    "TM": "Туркменистан",
    "AZ": "Азербайджан",
    "AM": "Армения",
    "GE": "Грузия",
    "MD": "Молдова",
    "LV": "Латвия",
    "LT": "Литва",
    "EE": "Эстония",
}

COUNTRY_CODES: tuple[str, ...] = tuple(COUNTRY_NAMES_RU)


@dataclass(frozen=True)
class Admin1:
    """Регион первого уровня: область, край, республика, вилайет."""

    code: str  # «RU.38»
    geoname_id: int
    name_en: str


def load_admin1_codes(path: Path) -> dict[str, Admin1]:
    """Регионы из `admin1CodesASCII.txt`, только нужные страны."""
    result: dict[str, Admin1] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        code = parts[0]
        if code.split(".")[0] not in COUNTRY_NAMES_RU:
            continue
        try:
            geoname_id = int(parts[3])
        except ValueError:
            continue
        result[code] = Admin1(code=code, geoname_id=geoname_id, name_en=parts[1].strip())
    return result


def region_name_ru(
    country_code: str,
    admin1_code: str | None,
    *,
    admin1_codes: dict[str, Admin1],
    official_names: dict[int, str],
) -> str | None:
    """Название региона по-русски или None, если региона нет в источнике."""
    if not admin1_code:
        return None

    if country_code == "RU":
        from astra.places.ru_admin1 import RU_ADMIN1_RU

        curated = RU_ADMIN1_RU.get(admin1_code)
        if curated:
            return curated

    entry = admin1_codes.get(f"{country_code}.{admin1_code}")
    if entry is None:
        return None
    return official_names.get(entry.geoname_id) or entry.name_en or None


def country_name_ru(country_code: str) -> str:
    return COUNTRY_NAMES_RU.get(country_code, country_code)
