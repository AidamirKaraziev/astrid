"""Как у места появляется русское название — и почему не «первое попавшееся».

## Что было

Основной дамп GeoNames кладёт все синонимы места в одно поле без языковых
меток: `Sokol,Sokal,Сокал,Сокол`. Импортёр брал оттуда первый кириллический
вариант — и в справочник уезжало то, что стояло первым по алфавиту чужого
языка. Живая база до переделки:

    Санкт-Петербург → Бетъырбух      Пермь       → Молотов
    Владикавказ     → Буро-ГӀала     Самара      → Куйбышев
    Череповец       → Чарапавец      Красноярск  → Краснодор
    Нижний Новгород → Горький        Донецк      → Город миллиона роз

Тридцать из сорока крупнейших городов пятнадцати стран были подписаны
неверно. Человек, набравший «Владикавказ», не находил город с населением
в триста тысяч и упирался в тупик посреди онбординга.

## Что теперь

Названия берутся из отдельного файла GeoNames, где у каждого варианта есть
язык и признаки: «предпочтительное», «краткое», «разговорное»,
«историческое». Ленинград и Молотов помечены историческими, Питер —
разговорным, и основным именем стать уже не могут.

Порядок ступеней (`resolve_place_name`):

1. официальное русское имя с пометкой «предпочтительное»;
2. просто русское имя;
3. краткое русское имя;
4. кириллица прямо в основном поле дампа;
5. синоним, чья транслитерация совпала с латинским написанием, —
   ступень, которая отличает «Сокол» от белорусского «Сокал»;
6. латиница как есть.

Шестая ступень — это четверть мест СНГ, у которых русского имени в
источнике нет вовсе. Придумывать им написание запрещено: машинная
транслитерация врёт, а ошибка в месте рождения человека недопустима.
Такие места находятся по русскому запросу через транслитерацию (см.
`astra.places.translit`), а на кнопке показывается исходное написание.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from astra.places.translit import has_cyrillic, latin_key

# Колонки alternateNamesV2.txt
_COL_GEONAME_ID = 1
_COL_LANGUAGE = 2
_COL_NAME = 3
_COL_PREFERRED = 4
_COL_SHORT = 5
_COL_COLLOQUIAL = 6
_COL_HISTORIC = 7

RUSSIAN = "ru"

# Чем больше, тем лучше. Разговорное и историческое не участвуют вовсе.
_RANK_PREFERRED = 3
_RANK_PLAIN = 2
_RANK_SHORT = 1


@dataclass(frozen=True)
class ResolvedName:
    """Имя места для показа человеку плюс всё, по чему его можно найти."""

    name: str
    is_latin: bool
    alternates: tuple[str, ...]

    @property
    def source(self) -> str:
        """Для логов импорта: какой ступенью закрылось имя."""
        return "latin" if self.is_latin else "russian"


# Буквы, которых в русском алфавите нет: і, ї, є, ў, ә, ғ и прочие выдают
# украинский, белорусский, казахский и языки Кавказа.
_RUSSIAN_LETTERS = frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def _flag(parts: list[str], index: int) -> bool:
    return len(parts) > index and parts[index] == "1"


def _is_russian_spelling(name: str) -> bool:
    letters = [ch for ch in name.lower() if ch.isalpha()]
    return bool(letters) and all(ch in _RUSSIAN_LETTERS for ch in letters)


def iter_official_names(
    path: Path,
    *,
    language: str = RUSSIAN,
) -> Iterator[tuple[int, tuple[int, int], str]]:
    """(geoname_id, ранг, название) по всем пригодным строкам файла.

    Отдельным генератором, потому что файл на 112 МБ и держать его в памяти
    целиком незачем: вызывающий сам решает, что оставить.
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= _COL_NAME or parts[_COL_LANGUAGE] != language:
                continue
            if _flag(parts, _COL_COLLOQUIAL) or _flag(parts, _COL_HISTORIC):
                continue
            name = parts[_COL_NAME].strip()
            if not name:
                continue
            if _flag(parts, _COL_PREFERRED):
                rank = _RANK_PREFERRED
            elif _flag(parts, _COL_SHORT):
                rank = _RANK_SHORT
            else:
                rank = _RANK_PLAIN
            # Кириллица важнее при равных флагах: у Ставрополя два русских
            # варианта без пометок — «Ставрополь» и латинское «Stavropol’»,
            # и без этого признака побеждал тот, что стоял в файле выше.
            yield int(parts[_COL_GEONAME_ID]), (rank, int(has_cyrillic(name))), name


def load_official_names(
    path: Path,
    *,
    needed: set[int] | None = None,
    language: str = RUSSIAN,
) -> dict[int, str]:
    """geoname_id → официальное название на нужном языке.

    `needed` сужает выборку до мест, которые мы реально импортируем: без него
    словарь распухает на весь мир, а нужны пятнадцать стран.
    """
    best: dict[int, tuple[tuple[int, int], str]] = {}
    for geoname_id, rank, name in iter_official_names(path, language=language):
        if needed is not None and geoname_id not in needed:
            continue
        current = best.get(geoname_id)
        if current is None or rank > current[0]:
            best[geoname_id] = (rank, name)
    return {geoname_id: name for geoname_id, (_, name) in best.items()}


def cyrillic_alternates(alternates: Iterable[str]) -> list[str]:
    """Кириллические синонимы без повторов — по ним тоже ищем.

    Повтором считаем совпадение по ключу поиска, а не по буквам: «Казань» и
    «Казан» ищутся одинаково, второй в индексе лишний. Из таких пар остаётся
    русское написание — иначе украинский «Іжевськ» вытеснил бы «Ижевск»
    просто потому, что стоял в списке раньше.
    """
    kept: dict[str, str] = {}
    for raw in alternates:
        name = raw.strip()
        if len(name) < 2 or not has_cyrillic(name):
            continue
        key = latin_key(name)
        current = kept.get(key)
        if current is None or (
            _is_russian_spelling(name) and not _is_russian_spelling(current)
        ):
            kept[key] = name
    return list(kept.values())


def closest_cyrillic_alternate(alternates: Iterable[str], ascii_name: str) -> str | None:
    """Синоним, чья транслитерация ближе всего к латинскому написанию.

    Ради этой функции всё и затевалось на пятой ступени: у города Сокол в
    синонимах лежат и «Сокол», и «Сокал». Латинское написание из того же
    источника — `Sokol`; совпадает с ним только первый.
    """
    target = latin_key(ascii_name)
    if not target:
        return None

    best: tuple[tuple[int, int, int], str] | None = None
    for name in cyrillic_alternates(alternates):
        candidate = latin_key(name)
        if candidate == target:
            score = 2
        elif candidate[:4] == target[:4]:
            score = 1
        else:
            score = 0
        # Ничьи разводим двумя признаками. Русские буквы важнее: «Ижевск» и
        # украинский «Іжевськ» транслитерируются одинаково, а нужен первый.
        # Затем — близость по длине: лишние или недостающие буквы обычно
        # означают чужой язык.
        ranked = (score, int(_is_russian_spelling(name)), -abs(len(candidate) - len(target)))
        if best is None or ranked > best[0]:
            best = (ranked, name)
    return best[1] if best is not None else None


def resolve_place_name(
    *,
    ascii_name: str,
    alternates: Iterable[str],
    official_name: str | None,
) -> ResolvedName:
    """Имя места по цепочке ступеней из докстринга модуля."""
    alternates = list(alternates)
    extra = tuple(cyrillic_alternates(alternates))

    if official_name:
        return ResolvedName(official_name.strip(), is_latin=False, alternates=extra)

    ascii_name = ascii_name.strip()
    if has_cyrillic(ascii_name):
        return ResolvedName(ascii_name, is_latin=False, alternates=extra)

    closest = closest_cyrillic_alternate(alternates, ascii_name)
    if closest is not None:
        return ResolvedName(closest, is_latin=False, alternates=extra)

    return ResolvedName(ascii_name, is_latin=True, alternates=extra)
