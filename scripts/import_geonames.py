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
    from astra.places.control_list import ALL_CASES, verify_catalog
    from astra.places.geonames_import import import_places

    init_engine()
    session_factory = get_session_factory()
    result = await import_places(session_factory, data_dir=ROOT / "data" / "geonames")

    print(f"\nМест в справочнике: {result.imported} из {result.countries} стран")
    print(f"  с ориентиром «N км от города»: {result.with_landmark}")
    print(f"  без русского названия в источнике: {result.latin_names}")
    if result.removed:
        print(f"  убрано выпавших из источника: {result.removed}")
    if result.kept_in_use:
        print(f"  оставлено (кто-то там родился): {result.kept_in_use}")

    # Приёмка сразу после импорта: справочник уже ломался молча, и единственный
    # момент, когда это можно поймать, — пока никто ещё не искал в нём город.
    async with session_factory() as session:
        failures = await verify_catalog(session)

    print(f"\nКонтрольный список: {len(ALL_CASES)} городов")
    if failures:
        print(f"  ПРОВАЛОВ: {len(failures)}")
        for line in failures:
            print(f"    {line}")
        sys.exit(1)
    print("  все находятся первой строкой")


if __name__ == "__main__":
    asyncio.run(run_import())
