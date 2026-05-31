"""Импорт населённых пунктов РФ из GeoNames и автозагрузка справочника."""

from __future__ import annotations

import asyncio
import logging
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from astra.places.models import Place
from astra.places.normalize import (
    build_display_name,
    build_search_text,
    normalize_place_query,
    resolve_russian_place_name,
)
from astra.places.ru_admin1 import admin1_name_ru, load_admin1_english

logger = logging.getLogger(__name__)

GEONAMES_RU_ZIP_URL = "https://download.geonames.org/export/dump/RU.zip"
GEONAMES_ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

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

BATCH_SIZE = 2000
DOWNLOAD_TIMEOUT = 300.0

_import_lock = asyncio.Lock()


def geonames_data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "geonames"


@dataclass(frozen=True)
class ImportResult:
    imported: int
    skipped: int
    truncated: bool


def parse_ru_line(line: str, admin1_names: dict[str, str]) -> dict | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 18:
        return None
    if parts[6] != "P" or parts[7] not in PPL_FEATURES:
        return None
    if parts[8] != "RU":
        return None

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


async def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading GeoNames file: %s → %s", url, dest)
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)


async def ensure_geonames_data_files(data_dir: Path | None = None) -> Path:
    """Скачивает RU.txt и admin1CodesASCII.txt, если их нет локально."""
    root = data_dir or geonames_data_dir()
    ru_file = root / "RU.txt"
    admin1_file = root / "admin1CodesASCII.txt"

    if not ru_file.exists():
        zip_path = root / "RU.zip"
        await _download_file(GEONAMES_RU_ZIP_URL, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extract("RU.txt", root)
        logger.info("Extracted %s", ru_file)

    if not admin1_file.exists():
        await _download_file(GEONAMES_ADMIN1_URL, admin1_file)

    return ru_file


async def _count_places(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Place))
    return int(result.scalar_one())


async def import_places_from_file(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ru_file: Path,
    admin1_file: Path,
    truncate: bool = False,
) -> ImportResult:
    admin1_names = load_admin1_english(admin1_file)
    batch: list[dict] = []
    total = 0
    skipped = 0

    if truncate:
        async with session_factory() as session:
            await session.execute(
                text(
                    "UPDATE profiles SET birth_place_id = NULL, notification_place_id = NULL",
                ),
            )
            await session.execute(text("DELETE FROM places"))
            await session.commit()

    async with session_factory() as session:
        with ru_file.open(encoding="utf-8") as fh:
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
                        logger.info("GeoNames import progress: %s places", total)

        if batch:
            stmt = insert(Place).values(batch)
            stmt = stmt.on_conflict_do_nothing(index_elements=["geoname_id"])
            await session.execute(stmt)
            await session.commit()
            total += len(batch)

    logger.info(
        "GeoNames import finished: imported=%s skipped=%s truncate=%s",
        total,
        skipped,
        truncate,
    )
    return ImportResult(imported=total, skipped=skipped, truncated=truncate)


async def ensure_places_catalog(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    data_dir: Path | None = None,
) -> bool:
    """
    Гарантирует наличие справочника мест в БД.

    Если таблица пуста — скачивает GeoNames (при необходимости) и импортирует данные.
    Возвращает True, если в БД есть хотя бы одна запись.
    """
    async with session_factory() as session:
        if await _count_places(session) > 0:
            return True

    async with _import_lock:
        async with session_factory() as session:
            if await _count_places(session) > 0:
                return True

        root = data_dir or geonames_data_dir()
        try:
            ru_file = await ensure_geonames_data_files(root)
            admin1_file = root / "admin1CodesASCII.txt"
            await import_places_from_file(
                session_factory,
                ru_file=ru_file,
                admin1_file=admin1_file,
                truncate=False,
            )
        except Exception:
            logger.exception("GeoNames auto-import failed")
            return False

        async with session_factory() as session:
            return await _count_places(session) > 0
