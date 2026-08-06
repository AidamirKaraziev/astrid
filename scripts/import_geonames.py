#!/usr/bin/env python3
"""Импорт справочника мест: пятнадцать постсоветских стран из GeoNames.

Данные скачиваются автоматически, если их нет в `data/geonames/`.

Повторный запуск **обновляет** записи по `geoname_id`, а не пересоздаёт их:
`places.id` лежит в `profiles.birth_place_id`, и пересоздание строк стёрло бы
людям место рождения вместе с натальными картами.

Запуск:
  uv run python scripts/import_geonames.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def run_import() -> None:
    sys.path.insert(0, str(ROOT / "src"))

    from astra.db.session import get_session_factory, init_engine
    from astra.places.geonames_import import import_places

    init_engine()
    result = await import_places(get_session_factory(), data_dir=ROOT / "data" / "geonames")

    print(f"\nМест в справочнике: {result.imported} из {result.countries} стран")
    print(f"  с ориентиром «N км от города»: {result.with_landmark}")
    print(f"  без русского названия в источнике: {result.latin_names}")


if __name__ == "__main__":
    asyncio.run(run_import())
