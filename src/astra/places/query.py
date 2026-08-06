"""Разбор того, что человек написал в поле ввода города.

Люди не пишут «Советское». Они пишут «село советское краснодарский край»,
«г. Москва», «ст-ца Калининская» или «Краснадар» с опечаткой. Задача модуля —
вытащить из этого название и, если оно есть, регион: тогда поиск сравнивает
названия с названиями, а не топит запрос в лишних словах.

Почему это важно для ранжирования: слово «село» в запросе размывает
похожесть, и «Советское» проигрывало посёлку, у которого в синонимах
случайно оказалось что-то созвучное. Служебные слова выбрасываются до
сравнения.
"""

from __future__ import annotations

from dataclasses import dataclass

from astra.places.normalize import normalize_place_query
from astra.places.translit import latin_key

# Тип населённого пункта: в названии его нет, для поиска это шум.
SETTLEMENT_WORDS = frozenset(
    {
        "город", "г", "гор",
        "село", "с", "сел",
        "деревня", "дер", "д",
        "посёлок", "поселок", "пос", "п", "пгт", "рп",
        "станица", "стца", "ст-ца", "ст",
        "хутор", "х", "хут",
        "аул", "кишлак", "аал", "улус", "слобода", "сл",
        "местечко", "мест",
    },
)

# Слова, которые ставятся после названия региона: «Липецкая область».
REGION_SUFFIX_WORDS = frozenset(
    {"область", "обл", "край", "округ", "ао", "губерния", "вобласць", "уезд", "марз"},
)

# Слова, которые ставятся перед названием региона: «Республика Татарстан».
REGION_PREFIX_WORDS = frozenset({"республика", "респ", "вилоят", "велаят", "аймак"})

_PUNCTUATION = str.maketrans({".": " ", "-": "-", "—": " ", "–": " "})


@dataclass(frozen=True)
class PlaceQuery:
    """Что человек искал, разобранное на части."""

    raw: str
    name: str
    name_latin: str
    region: str | None
    # Регион без слов «область», «край», «республика». Сравнивать с ними
    # нельзя: у «Липецкой области» и «Львовской области» общего слова хватает
    # на схожесть 0,46, и любой регион совпадал с любым.
    region_key: str | None

    @property
    def is_searchable(self) -> bool:
        """Меньше двух букв искать бессмысленно: совпадёт полсправочника."""
        return len(self.name) >= 2

    @property
    def prefix(self) -> str:
        return f"{self.name}%"

    @property
    def prefix_latin(self) -> str:
        return f"{self.name_latin}%"


def _tokens(text: str) -> list[str]:
    cleaned = normalize_place_query(text.translate(_PUNCTUATION))
    return [word for word in cleaned.split() if word]


def _split_region(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Разделить на название и регион по словам-маркерам."""
    for index, token in enumerate(tokens):
        if token in REGION_SUFFIX_WORDS and index > 0:
            # «липецкая область» — маркер идёт после названия региона, и всё
            # до него на одно слово назад тоже относится к региону.
            return tokens[: index - 1], tokens[index - 1 :]
        if token in REGION_PREFIX_WORDS:
            # «республика татарстан» — маркер первый, регион идёт за ним.
            return tokens[:index], tokens[index:]
    return tokens, []


def parse_place_query(text: str) -> PlaceQuery:
    """«село советское краснодарский край» → имя «советское», регион «краснодарский край»."""
    raw = text.strip()

    head, region_tokens = _tokens(raw), []
    if "," in raw:
        # Запятая — самый надёжный разделитель: человек сам показал границу.
        first, _, rest = raw.partition(",")
        head, region_tokens = _tokens(first), _tokens(rest)
    else:
        head, region_tokens = _split_region(_tokens(raw))

    # Тип населённого пункта выбрасываем, но только если после этого что-то
    # останется: «Село» — реальное название деревни в Карелии.
    without_service = [word for word in head if word not in SETTLEMENT_WORDS]
    name_tokens = without_service or head

    name = " ".join(name_tokens)
    region = " ".join(region_tokens) or None
    region_key = (
        " ".join(
            word
            for word in region_tokens
            if word not in REGION_SUFFIX_WORDS and word not in REGION_PREFIX_WORDS
        )
        or None
    )
    return PlaceQuery(
        raw=raw,
        name=name,
        name_latin=latin_key(name),
        region=region,
        region_key=region_key,
    )
