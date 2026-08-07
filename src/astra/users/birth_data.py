"""Чего не хватает профилю, чтобы открыть продукт.

Онбординг больше не собирает дату, время и место рождения: человек попадает
в базу, назвав имя и пол, а астроданные добираются в тот момент, когда он
открывает то, чему они нужны. Значит, у каждого продукта появляется вопрос
«а хватит ли данных» — и отвечать на него россыпью проверок `is None` по
двум десяткам файлов нельзя: часть мест такую проверку неизбежно забудет, и
человек увидит либо падение, либо разбор, посчитанный от Москвы и полудня.

Здесь два разных вопроса, и путать их не нужно:

* `blocked_by` — без чего продукт невозможен. Пусто — можно считать.
* `missing_for` — что вообще стоит спросить, включая необязательное.

Время рождения именно необязательно: без него карта считается на полдень,
теряются асцендент и дома, но знаки планет остаются верными — и человеку,
который своего времени не знает, дверь закрывать нельзя. Место ведёт себя
иначе: при пустом месте координаты подставляются московские
(`astro_service.birth_coordinates`), и разбор домов от чужого города — это
не «менее точно», а неправда. Поэтому место обязательно там, где дома
считаются.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from astra.users.models import Profile


class BirthField(StrEnum):
    """Данные рождения, которые спрашиваются у человека по отдельности."""

    DATE = "birth_date"
    TIME = "birth_time"
    PLACE = "birth_place"


class Product(StrEnum):
    """Продукты, которым нужны данные рождения.

    Карта дня, таро-расклады и колесо сюда не входят: они не смотрят в
    профиль вовсе, и человек сразу после короткого онбординга открывает их
    без единого вопроса. Это и есть смысл всей затеи — сначала ценность,
    потом анкета.
    """

    DAILY_PREDICTION = "daily_prediction"
    NATAL_REPORT = "natal_report"
    COMPATIBILITY = "compatibility"
    ASK_ANSWER = "ask_answer"
    PROFILE_PORTRAIT = "profile_portrait"


@dataclass(frozen=True)
class BirthDataNeed:
    """Что продукт требует, а что лишь просит.

    `optional` — то, что спрашиваем, но пропуск не закрывает дверь: человек
    отвечает «не знаю», и продукт считается с меньшей точностью.
    """

    required: tuple[BirthField, ...]
    optional: tuple[BirthField, ...] = ()


NEEDS: dict[Product, BirthDataNeed] = {
    # Предсказание строится от знака Солнца — хватает одной даты.
    Product.DAILY_PREDICTION: BirthDataNeed(required=(BirthField.DATE,)),
    Product.NATAL_REPORT: BirthDataNeed(
        required=(BirthField.DATE, BirthField.PLACE),
        optional=(BirthField.TIME,),
    ),
    Product.COMPATIBILITY: BirthDataNeed(
        required=(BirthField.DATE, BirthField.PLACE),
        optional=(BirthField.TIME,),
    ),
    # Каждый вопрос «Спроси Астрид» считает своё, и часть из них обходится
    # знаками планет без домов. Общий минимум — дата; всё сверх того продукт
    # добирает сам через собственный расчёт.
    Product.ASK_ANSWER: BirthDataNeed(
        required=(BirthField.DATE,),
        optional=(BirthField.TIME, BirthField.PLACE),
    ),
    Product.PROFILE_PORTRAIT: BirthDataNeed(required=(BirthField.DATE,)),
}


class BirthDataMissing(RuntimeError):
    """Расчёт запросили без данных, на которых он держится.

    Отдельное исключение, а не `AttributeError: 'NoneType' has no attribute
    'year'`: в логах должно быть видно, что это не поломка расчёта, а
    пропущенная проверка на входе в продукт.
    """

    def __init__(self, fields: tuple[BirthField, ...]) -> None:
        self.fields = fields
        super().__init__(f"нет данных рождения: {', '.join(fields)}")


def _has(profile: Profile | None, field: BirthField) -> bool:
    if profile is None:
        return False
    if field is BirthField.DATE:
        return profile.birth_date is not None
    if field is BirthField.TIME:
        return profile.birth_time is not None
    # Именно ссылка на справочник, а не текстовое `birth_place`: без неё
    # координат нет, и расчёт молча уезжает в Москву.
    return profile.birth_place_id is not None


def blocked_by(product: Product, profile: Profile | None) -> tuple[BirthField, ...]:
    """Без чего продукт невозможен. Пустой ответ — можно считать."""
    need = NEEDS[product]
    return tuple(field for field in need.required if not _has(profile, field))


def missing_for(product: Product, profile: Profile | None) -> tuple[BirthField, ...]:
    """Что стоит спросить перед продуктом, включая необязательное.

    Порядок ответа — порядок вопросов человеку: сначала обязательное, потом
    то, что уточняет точность.
    """
    need = NEEDS[product]
    return tuple(
        field for field in (*need.required, *need.optional) if not _has(profile, field)
    )


def has_birth_data(profile: Profile | None) -> bool:
    """Есть ли у профиля хоть какая-то астрооснова.

    Ровно один вопрос: можно ли вообще что-то посчитать. Для более тонких
    решений есть `blocked_by` — он говорит про конкретный продукт.
    """
    return _has(profile, BirthField.DATE)
