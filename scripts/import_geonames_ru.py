#!/usr/bin/env python3
"""
Импорт населённых пунктов РФ из GeoNames (бесплатно).

Данные скачиваются автоматически, если их нет в data/geonames/.
Повторный запуск очищает таблицу places и импортирует заново.

Запуск:
  uv run python scripts/import_geonames_ru.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def run_import() -> None:
    sys.path.insert(0, str(ROOT / "src"))

    from astra.db.session import get_session_factory, init_engine
    from astra.places.geonames_import import ensure_geonames_data_files, import_places_from_file

    init_engine()
    session_factory = get_session_factory()
    data_dir = ROOT / "data" / "geonames"

    ru_file = await ensure_geonames_data_files(data_dir)
    result = await import_places_from_file(
        session_factory,
        ru_file=ru_file,
        admin1_file=data_dir / "admin1CodesASCII.txt",
        truncate=True,
    )
    print(f"\nDone: {result.imported} places imported, {result.skipped} lines skipped.")


if __name__ == "__main__":
    asyncio.run(run_import())
