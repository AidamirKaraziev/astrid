#!/usr/bin/env python3
"""
Импорт населённых пунктов РФ из GeoNames (бесплатно).

1. Скачайте https://download.geonames.org/export/dump/RU.zip
2. Распакуйте RU.txt в data/geonames/RU.txt
3. (опционально) admin1CodesASCII.txt → data/geonames/admin1CodesASCII.txt

Запуск:
  uv run python scripts/import_geonames_ru.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path

# populated place feature codes (города, деревни, посёлки)
PPL_FEATURES = frozenset(
    {
        "PPL",
        "PPLA",
        "PPLA2",
        "PPLA3",
        "PPLA4",
        "PPLC",
        "PPLF",
        "PPLG",
        "PPLH",
        "PPLQ",
        "PPLR",
        "PPLS",
        "PPLW",
        "PPLX",
    },
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "geonames"
RU_FILE = DATA_DIR / "RU.txt"
ADMIN1_FILE = DATA_DIR / "admin1CodesASCII.txt"

BATCH_SIZE = 2000


def load_admin1_names() -> dict[str, str]:
    from astra.places.ru_admin1 import load_admin1_english

    return load_admin1_english(ADMIN1_FILE)


def parse_ru_line(line: str, admin1_names: dict[str, str]) -> dict | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 18:
        return None
    if parts[6] != "P" or parts[7] not in PPL_FEATURES:
        return None
    if parts[8] != "RU":
        return None

    from astra.places.normalize import (
        build_display_name,
        build_search_text,
        normalize_place_query,
        resolve_russian_place_name,
    )
    from astra.places.ru_admin1 import admin1_name_ru

    name_ascii = parts[1]
    alternates = parts[3]
    name_ru, cyrillic_alternates = resolve_russian_place_name(name_ascii, alternates)

    admin1_code = parts[10] or None
    admin1_en = admin1_names.get(admin1_code) if admin1_code else None
    admin1_ru = admin1_name_ru(admin1_code, admin1_en)

    search_text = build_search_text(
        name_ru=name_ru,
        name_ascii=name_ascii,
        cyrillic_alternates=cyrillic_alternates,
        admin1_ru=admin1_ru,
    )
    tz = parts[17] or "Europe/Moscow"

    return {
        "id": uuid.uuid4(),
        "geoname_id": int(parts[0]),
        "name": name_ru,
        "name_normalized": normalize_place_query(name_ru),
        "display_name": build_display_name(name_ru, admin1_ru),
        "search_text": search_text,
        "country_code": "RU",
        "admin1_code": admin1_code,
        "admin1_name": admin1_ru,
        "feature_code": parts[7],
        "latitude": Decimal(parts[4]),
        "longitude": Decimal(parts[5]),
        "timezone": tz,
        "population": int(parts[14]) if parts[14] else 0,
    }


async def run_import() -> None:
    if not RU_FILE.exists():
        print(f"File not found: {RU_FILE}")
        print("Download RU.zip from https://download.geonames.org/export/dump/RU.zip")
        sys.exit(1)

    sys.path.insert(0, str(ROOT / "src"))
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from astra.db.session import get_session_factory, init_engine
    from astra.places.models import Place

    admin1_names = load_admin1_names()
    init_engine()
    session_factory = get_session_factory()

    batch: list[dict] = []
    total = 0
    skipped = 0

    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE profiles SET birth_place_id = NULL, notification_place_id = NULL",
            ),
        )
        await session.execute(text("DELETE FROM places"))
        await session.commit()

    async with session_factory() as session:
        with RU_FILE.open(encoding="utf-8") as fh:
            for line in fh:
                row = parse_ru_line(line, admin1_names)
                if row is None:
                    skipped += 1
                    continue
                batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    stmt = insert(Place).values(batch)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["geoname_id"])
                    await session.execute(stmt)
                    await session.commit()
                    total += len(batch)
                    batch.clear()
                    if total % 20000 == 0:
                        print(f"  imported {total}...")

        if batch:
            stmt = insert(Place).values(batch)
            stmt = stmt.on_conflict_do_nothing(index_elements=["geoname_id"])
            await session.execute(stmt)
            await session.commit()
            total += len(batch)

    print(f"\nDone: {total} places imported, {skipped} lines skipped.")


if __name__ == "__main__":
    asyncio.run(run_import())
