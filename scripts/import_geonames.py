#!/usr/bin/env python3
"""Переимпорт справочника мест — обёртка над командой `astra-places`.

Оставлена для удобства локальной работы: на сервере той же командой служит
точка входа `astra-places` (`docker compose exec api astra-places`), потому
что папка `scripts/` в образ не копируется.

    uv run python scripts/import_geonames.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from astra.places.cli import reimport_places

    sys.exit(asyncio.run(reimport_places(ROOT / "data" / "geonames")))


if __name__ == "__main__":
    main()
