"""Импорт справочника мест: пятнадцать постсоветских стран из GeoNames.

## Что было не так

Импортёр брал только Россию и называл места первым попавшимся кириллическим
синонимом из общей свалки без языковых меток. В проде это выглядело так:
Санкт-Петербург лежал как «Бетъырбух», Владикавказ как «Буро-ГӀала», Пермь
как «Молотов», Череповец как «Чарапавец» — и не находился вовсе. Тридцать из
сорока крупнейших городов были подписаны неверно, а родившиеся в Казахстане,
Украине или Грузии не могли пройти онбординг в принципе.

## Что теперь

* пятнадцать стран вместо одной — 337 тысяч мест вместо 203 тысяч;
* имена из отдельного файла с языковыми метками (`astra.places.names`):
  историческое и разговорное основным именем стать не могут;
* латинский ключ рядом с каждым именем, чтобы четверть мест без русского
  написания находилась по русскому запросу (`astra.places.translit`);
* ориентир «12 км от Устюжны» для различения тёзок (`astra.places.nearest`);
* обновление через upsert по `geoname_id`. **Никакого TRUNCATE:** прежний
  переимпорт обнулял `birth_place_id` у всех живых профилей, то есть стирал
  людям место рождения и ломал их натальные карты.

## Чего намеренно не берём

Фермы, урочища и микрорайоны. Из семнадцати тысяч таких записей собственное
имя есть у восьмисот, остальное — «Отделение Совхоза Номер Три» и «Урочище
Раменский Мох»: узнавать там нечего, а списки тёзок они засоряют. Микрорайоны
(`PPLX`) — причина, по которой на «Санкт-Петербург» бот отвечал «Калининский,
Красногвардейский, Центральный».

Упразднённые сёла (`PPLQ`), наоборот, оставляем: расселённая в девяностых
деревня — это чьё-то место рождения.
"""

from __future__ import annotations

import asyncio
import uuid
import zipfile
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from astra.core.observability import Event, get_logger
from astra.places.models import Place
from astra.places.names import load_official_names, resolve_place_name
from astra.places.nearest import Landmark, LandmarkIndex
from astra.places.normalize import build_display_name, normalize_place_query
from astra.places.regions import (
    COUNTRY_CODES,
    country_name_ru,
    load_admin1_codes,
    region_name_ru,
)
from astra.places.translit import latin_key

log = get_logger(__name__)

GEONAMES_BASE_URL = "https://download.geonames.org/export/dump"
ALTERNATE_NAMES_FILE = "alternateNamesV2"
ADMIN1_FILE = "admin1CodesASCII.txt"

# Что считаем населённым пунктом. PPLX (микрорайоны), FRM (фермы) и AREA
# (урочища) сюда не входят осознанно — см. докстринг модуля.
PLACE_FEATURES = frozenset(
    {
        "PPL",  # обычный населённый пункт, сюда же попадают хутора
        "PPLA",  # центр региона
        "PPLA2",  # центр района
        "PPLA3",
        "PPLA4",
        "PPLA5",
        "PPLC",  # столица
        "PPLF",  # посёлок при хозяйстве
        "PPLG",  # административный центр
        "PPLH",  # больше не существует
        "PPLQ",  # упразднённый
    },
)

# Ориентир берём из населённых пунктов такого размера: человек их знает —
# это городок, куда ездили в школу или в больницу. На пяти тысячах медиана
# расстояния выходит 27 км, на двадцати — уже 54 км и подпись бесполезна.
LANDMARK_MIN_POPULATION = 5_000
# Дальше этого ориентир ни о чём не говорит: «120 км от Шексны» не помогает
# узнать своё село, лучше показать строку без ориентира.
LANDMARK_MAX_KM = 100

BATCH_SIZE = 2000
DOWNLOAD_TIMEOUT = 600.0

# Postgres не принимает больше 32767 подстановок в одном запросе, а колонок у
# места девятнадцать. Размер пачки считаем от их числа, чтобы новая колонка
# не уронила импорт молча.
_MAX_QUERY_PARAMS = 32_767

_import_lock = asyncio.Lock()


def geonames_data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "geonames"


@dataclass(frozen=True)
class ImportResult:
    imported: int
    skipped: int
    countries: int
    latin_names: int
    with_landmark: int
    removed: int = 0
    kept_in_use: int = 0


# --------------------------------------------------------------------------
# Загрузка файлов
# --------------------------------------------------------------------------


async def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info(Event.GEONAMES_DOWNLOAD, url=url, dest=str(dest))
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)


async def _ensure_unpacked(root: Path, stem: str) -> Path:
    """Скачать и распаковать `<stem>.zip`, если `<stem>.txt` ещё нет."""
    target = root / f"{stem}.txt"
    if target.exists():
        return target
    archive = root / f"{stem}.zip"
    await _download(f"{GEONAMES_BASE_URL}/{stem}.zip", archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extract(f"{stem}.txt", root)
    log.info(Event.GEONAMES_EXTRACTED, file=str(target))
    return target


async def ensure_geonames_data_files(data_dir: Path | None = None) -> Path:
    """Дампы всех стран, файл названий и коды регионов на диске."""
    root = data_dir or geonames_data_dir()
    root.mkdir(parents=True, exist_ok=True)

    for country_code in COUNTRY_CODES:
        await _ensure_unpacked(root, country_code)
    await _ensure_unpacked(root, ALTERNATE_NAMES_FILE)

    admin1 = root / ADMIN1_FILE
    if not admin1.exists():
        await _download(f"{GEONAMES_BASE_URL}/{ADMIN1_FILE}", admin1)
    return root


# --------------------------------------------------------------------------
# Разбор
# --------------------------------------------------------------------------


@dataclass
class RawPlace:
    """Строка дампа до того, как у места появилось русское имя."""

    geoname_id: int
    ascii_name: str
    alternates: list[str]
    country_code: str
    admin1_code: str | None
    feature_code: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    population: int


def parse_dump_line(line: str) -> RawPlace | None:
    """Строка дампа страны → место, либо None, если это не населённый пункт."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 18:
        return None
    if parts[6] != "P" or parts[7] not in PLACE_FEATURES:
        return None
    country_code = parts[8]
    if country_code not in COUNTRY_CODES:
        return None
    try:
        geoname_id = int(parts[0])
        latitude = Decimal(parts[4])
        longitude = Decimal(parts[5])
    except (ValueError, ArithmeticError):
        return None

    return RawPlace(
        geoname_id=geoname_id,
        ascii_name=parts[1],
        alternates=parts[3].split(",") if parts[3] else [],
        country_code=country_code,
        admin1_code=parts[10] or None,
        feature_code=parts[7],
        latitude=latitude,
        longitude=longitude,
        timezone=parts[17] or None,
        population=int(parts[14]) if parts[14] else 0,
    )


def read_dumps(root: Path) -> list[RawPlace]:
    places: list[RawPlace] = []
    for country_code in COUNTRY_CODES:
        path = root / f"{country_code}.txt"
        if not path.exists():
            log.warning(Event.GEONAMES_IMPORT_PROGRESS, missing_country=country_code)
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                place = parse_dump_line(line)
                if place is not None:
                    places.append(place)
    return places


NAME_SEPARATOR = "|"


def build_name_index(name: str, alternates: tuple[str, ...]) -> str:
    """«|санкт-петербург|ленинград|питер|» — все имена места с границами.

    Разделители нужны, чтобы «Ленинград» находил Петербург (целое бывшее имя),
    но «Красное» не цепляло «Красное Эхо» — там это лишь слово внутри другого
    названия, и без границ счётчик тёзок раздувался втрое.
    """
    names = [normalize_place_query(value) for value in (name, *alternates)]
    unique = list(dict.fromkeys(part for part in names if part))
    return NAME_SEPARATOR + NAME_SEPARATOR.join(unique) + NAME_SEPARATOR


def build_search_blob(
    *,
    name: str,
    ascii_name: str,
    alternates: tuple[str, ...],
    region: str | None,
    country: str,
) -> str:
    parts = [name, ascii_name, *alternates]
    if region:
        parts.append(region)
    parts.append(country)
    return normalize_place_query(" ".join(parts))


def build_landmark_index(places: list[RawPlace]) -> LandmarkIndex:
    """Города-ориентиры. Имена подставляются позже, здесь нужны координаты."""
    return LandmarkIndex(
        Landmark(str(place.geoname_id), float(place.latitude), float(place.longitude))
        for place in places
        if place.population >= LANDMARK_MIN_POPULATION
    )


def build_rows(root: Path) -> tuple[list[dict], ImportResult]:
    """Все места пятнадцати стран, готовые к записи в базу."""
    raw = read_dumps(root)
    if not raw:
        msg = f"дампы GeoNames не найдены в {root}"
        raise FileNotFoundError(msg)

    official = load_official_names(root / f"{ALTERNATE_NAMES_FILE}.txt")
    admin1_codes = load_admin1_codes(root / ADMIN1_FILE)

    # Сначала имена: ориентир должен подписываться тем же названием, которое
    # человек увидит в списке, иначе «12 км от Cherepovets» рядом с
    # «Череповец» выглядит как два разных города.
    resolved = {
        place.geoname_id: resolve_place_name(
            ascii_name=place.ascii_name,
            alternates=place.alternates,
            official_name=official.get(place.geoname_id),
        )
        for place in raw
    }

    index = build_landmark_index(raw)
    log.info(Event.GEONAMES_IMPORT_PROGRESS, landmarks=len(index))

    rows: list[dict] = []
    latin_names = 0
    with_landmark = 0

    for place in raw:
        name = resolved[place.geoname_id].name
        alternates = resolved[place.geoname_id].alternates
        if resolved[place.geoname_id].is_latin:
            latin_names += 1

        region = region_name_ru(
            place.country_code,
            place.admin1_code,
            admin1_codes=admin1_codes,
            official_names=official,
        )
        country = country_name_ru(place.country_code)

        # Сам себе ориентиром не бывает: город размером с ориентир нашёл бы
        # себя на нулевом расстоянии, и два одноимённых городка остались бы
        # неразличимыми. Исключаем себя и берём следующий по близости.
        landmark = index.nearest(
            float(place.latitude),
            float(place.longitude),
            max_km=LANDMARK_MAX_KM,
            exclude=str(place.geoname_id),
        )
        nearest_city: str | None = None
        nearest_city_km: int | None = None
        if landmark is not None:
            nearest_city = resolved[int(landmark[0].name)].name
            nearest_city_km = round(landmark[1])
            with_landmark += 1

        search_text = build_search_blob(
            name=name,
            ascii_name=place.ascii_name,
            alternates=alternates,
            region=region,
            country=country,
        )

        rows.append(
            {
                "id": uuid.uuid4(),
                "geoname_id": place.geoname_id,
                "name": name,
                "name_normalized": normalize_place_query(name),
                "name_latin": latin_key(name),
                "display_name": build_display_name(name, region, country),
                "search_text": search_text,
                "search_latin": latin_key(search_text),
                "search_names": build_name_index(name, alternates),
                "nearest_city": nearest_city,
                "nearest_city_km": nearest_city_km,
                "country_code": place.country_code,
                "country_name": country,
                "admin1_code": place.admin1_code,
                "admin1_name": region,
                "feature_code": place.feature_code,
                "latitude": place.latitude,
                "longitude": place.longitude,
                "timezone": place.timezone or "Europe/Moscow",
                "population": place.population,
            },
        )

    result = ImportResult(
        imported=len(rows),
        skipped=0,
        countries=len({row["country_code"] for row in rows}),
        latin_names=latin_names,
        with_landmark=with_landmark,
    )
    return rows, result


# --------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------

# Всё, кроме `id`: подменять первичный ключ нельзя, на него ссылаются профили.
_UPDATABLE = (
    "name",
    "name_normalized",
    "name_latin",
    "display_name",
    "search_text",
    "search_latin",
    "search_names",
    "nearest_city",
    "nearest_city_km",
    "country_code",
    "country_name",
    "admin1_code",
    "admin1_name",
    "feature_code",
    "latitude",
    "longitude",
    "timezone",
    "population",
)


async def write_rows(
    session_factory: async_sessionmaker[AsyncSession],
    rows: list[dict],
) -> int:
    """Записать пачками, обновляя существующие места по `geoname_id`.

    Именно обновление, а не «удалить и залить заново»: `places.id` лежит в
    `profiles.birth_place_id`, и пересоздание строк стёрло бы людям место
    рождения вместе с их натальными картами.
    """
    if not rows:
        return 0

    batch_size = min(BATCH_SIZE, _MAX_QUERY_PARAMS // len(rows[0]))
    written = 0
    async with session_factory() as session:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            statement = insert(Place).values(batch)
            statement = statement.on_conflict_do_update(
                index_elements=["geoname_id"],
                set_={column: getattr(statement.excluded, column) for column in _UPDATABLE},
            )
            await session.execute(statement)
            await session.commit()
            written += len(batch)
            if written % 50_000 == 0:
                log.info(Event.GEONAMES_IMPORT_PROGRESS, places_count=written)
    return written


async def remove_stale(
    session_factory: async_sessionmaker[AsyncSession],
    keep: set[int],
) -> tuple[int, int]:
    """Убрать места, которых в источнике больше нет. Возвращает (удалено, оставлено).

    Обновление по `geoname_id` само по себе ничего не удаляет, и записи,
    выпавшие из состава справочника, остаются в базе навсегда. Так в выдаче и
    жили микрорайоны: на «Санкт-Петербург» бот отвечал «Калининский,
    Красногвардейский, Центральный».

    Место, которое кто-то уже выбрал местом рождения, не удаляем никогда:
    внешний ключ обнулил бы `birth_place_id`, и человек потерял бы натальную
    карту из-за смены состава справочника.
    """
    async with session_factory() as session:
        in_use = await session.execute(
            text(
                """
                SELECT p.geoname_id FROM places p
                WHERE p.id IN (SELECT birth_place_id FROM profiles WHERE birth_place_id IS NOT NULL)
                   OR p.id IN (
                       SELECT notification_place_id FROM profiles
                       WHERE notification_place_id IS NOT NULL
                   )
                   OR p.id IN (
                       SELECT birth_place_id FROM natal_profiles WHERE birth_place_id IS NOT NULL
                   )
                """,
            ),
        )
        protected = {row[0] for row in in_use}

        # Разницу считаем в Python: подстановок в запросе не может быть больше
        # 32767, а в справочнике триста тысяч мест.
        existing = await session.execute(select(Place.geoname_id))
        doomed = sorted({row[0] for row in existing} - keep - protected)
        chunk = _MAX_QUERY_PARAMS // 2
        for start in range(0, len(doomed), chunk):
            await session.execute(
                delete(Place).where(Place.geoname_id.in_(doomed[start : start + chunk])),
            )
        await session.commit()

    kept = len(protected - keep)
    if kept:
        log.info(Event.GEONAMES_IMPORT_PROGRESS, kept_in_use=kept)
    return len(doomed), kept


async def import_places(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    data_dir: Path | None = None,
) -> ImportResult:
    """Полный цикл: файлы на диск → разбор → запись → уборка выпавших."""
    root = await ensure_geonames_data_files(data_dir)
    rows, result = build_rows(root)
    await write_rows(session_factory, rows)
    removed, kept = await remove_stale(session_factory, {row["geoname_id"] for row in rows})
    result = replace(result, removed=removed, kept_in_use=kept)
    log.info(
        Event.GEONAMES_IMPORT_DONE,
        imported=result.imported,
        countries=result.countries,
        latin_names=result.latin_names,
        with_landmark=result.with_landmark,
        removed=result.removed,
        kept_in_use=result.kept_in_use,
    )
    return result


async def _count_places(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Place))
    return int(result.scalar_one())


async def ensure_places_catalog(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    data_dir: Path | None = None,
) -> bool:
    """Гарантировать непустой справочник. True — в базе есть хотя бы одно место."""
    async with session_factory() as session:
        if await _count_places(session) > 0:
            return True

    async with _import_lock:
        async with session_factory() as session:
            if await _count_places(session) > 0:
                return True
        try:
            await import_places(session_factory, data_dir=data_dir)
        except Exception:
            log.exception(Event.GEONAMES_IMPORT_FAILED)
            return False

    async with session_factory() as session:
        return await _count_places(session) > 0
