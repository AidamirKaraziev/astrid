"""Команда переимпорта справочника мест: `astra-places`.

Живёт в пакете, а не в `scripts/`, по простой причине: `scripts/` не
копируется в образ, и на сервере файла просто нет. Через точку входа команда
доступна везде, где установлен пакет:

    docker compose exec api astra-places

Что делает:

1. качает дампы пятнадцати стран и файл официальных названий, если их нет;
2. обновляет записи по `geoname_id` — места рождения людей не теряются;
3. убирает выпавшие из источника, кроме тех, где кто-то родился;
4. прогоняет контрольный список известных городов и **падает**, если хоть
   один не находится первой строкой.

Четвёртый шаг — не формальность. Справочник уже ломался молча: Петербург
лежал под именем «Бетъырбух», Череповец не находился вовсе, и это доехало до
живых людей. Поэтому импорт, после которого известный город не ищется,
считается неудавшимся.

Памяти нужно около гигабайта: разбор держит все 337 тысяч мест сразу, иначе
не посчитать ближайший город-ориентир. На сервере с восемью гигабайтами лучше
запускать, остановив `api` и `worker`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def reimport_places(data_dir: Path | None = None) -> int:
    """Переимпорт с приёмкой. Возвращает код выхода."""
    from astra.db.session import get_session_factory, init_engine
    from astra.places.control_list import ALL_CASES, verify_catalog
    from astra.places.geonames_import import import_places

    init_engine()
    session_factory = get_session_factory()
    result = await import_places(session_factory, data_dir=data_dir)

    print(f"\nМест в справочнике: {result.imported} из {result.countries} стран")
    print(f"  с ориентиром «N км от города»: {result.with_landmark}")
    print(f"  без русского названия в источнике: {result.latin_names}")
    if result.removed:
        print(f"  убрано выпавших из источника: {result.removed}")
    if result.kept_in_use:
        print(f"  оставлено, потому что там кто-то родился: {result.kept_in_use}")

    async with session_factory() as session:
        failures = await verify_catalog(session)

    print(f"\nКонтрольный список: {len(ALL_CASES)} городов")
    if failures:
        print(f"  ПРОВАЛОВ: {len(failures)}")
        for line in failures:
            print(f"    {line}")
        return 1
    print("  все находятся первой строкой")
    return 0


def run() -> None:
    sys.exit(asyncio.run(reimport_places()))


if __name__ == "__main__":
    run()
