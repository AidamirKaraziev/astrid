"""Ближайший город-ориентир — третий уровень адреса, которого нет в данных.

## Зачем

Двадцать восемь процентов справочника — тёзки, неразличимые на глаз. В одной
Вологодской области тридцать восемь деревень «Горка», и в списке они выглядят
тридцатью восемью одинаковыми строками. Человек не может выбрать свою, даже
когда она перед ним.

Напрашивающийся выход — показать район. Но в GeoNames район заполнен у 1,3%
записей, а сами районы лежат точками, а не границами: вычислить попадание
нельзя, только «ближайший центр», а это регулярно даёт неверный район. Врать
в адресе места рождения нельзя.

Поэтому третий уровень мы считаем сами и отвечаем за него: «Горка · 12 км от
Устюжны». Ориентир человек узнаёт — это городок, куда ездили в школу или в
больницу.

Проверено на худшей группе страны: все тридцать восемь «Горок» получают
разные подписи, медиана расстояния 27 км.

## Как

Перебирать каждую деревню против всех городов — это 337 тысяч на пять тысяч,
почти два миллиарда расчётов. Вместо этого точки раскладываются по сетке, и
для каждой просматриваются только соседние клетки, кольцами наружу. Кольца
обходятся, пока ближайшая возможная точка следующего кольца не окажется
дальше уже найденного, — тогда ответ точный, а не приблизительный.

Сетка трёхмерная, по координатам на сфере. Плоская карта здесь не годится:
градус долготы у Краснодара — сто километров, у Мурманска — сорок, и любая
попытка растянуть их в общую плоскость даёт разное искажение на юге и на
севере. В трёх измерениях расстояние по хорде монотонно связано с
расстоянием по поверхности, поэтому ближайший по хорде — он же ближайший
по-настоящему.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0

# Клетка сетки. Пятьдесят километров — компромисс: мельче даёт много пустых
# колец, крупнее раздувает список кандидатов в клетке.
_CELL_KM = 50.0

Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class Landmark:
    """Город-ориентир, по которому человек узнаёт своё село."""

    name: str
    latitude: float
    longitude: float


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по большому кругу."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


def _to_sphere(latitude: float, longitude: float) -> Point3D:
    """Точка на сфере в километрах от центра Земли."""
    phi = math.radians(latitude)
    lam = math.radians(longitude)
    cos_phi = math.cos(phi)
    return (
        EARTH_RADIUS_KM * cos_phi * math.cos(lam),
        EARTH_RADIUS_KM * cos_phi * math.sin(lam),
        EARTH_RADIUS_KM * math.sin(phi),
    )


def _chord_to_surface(chord_km: float) -> float:
    """Хорда → расстояние по поверхности. Связь монотонная, порядок сохраняется."""
    ratio = min(1.0, chord_km / (2 * EARTH_RADIUS_KM))
    return 2 * EARTH_RADIUS_KM * math.asin(ratio)


class LandmarkIndex:
    """Сетка ориентиров с точным поиском ближайшего."""

    def __init__(self, landmarks: Iterable[Landmark]) -> None:
        self._cells: dict[tuple[int, int, int], list[tuple[Point3D, Landmark]]] = {}
        self._size = 0
        for landmark in landmarks:
            point = _to_sphere(landmark.latitude, landmark.longitude)
            self._cells.setdefault(self._cell_of(point), []).append((point, landmark))
            self._size += 1
        # Дальше этого радиуса колец не бывает: диаметр Земли, поделённый на
        # клетку. Страховка от бесконечного цикла на пустой стороне планеты.
        self._max_radius = int(2 * EARTH_RADIUS_KM / _CELL_KM) + 2

    def __len__(self) -> int:
        return self._size

    @staticmethod
    def _cell_of(point: Point3D) -> tuple[int, int, int]:
        return (
            int(point[0] // _CELL_KM),
            int(point[1] // _CELL_KM),
            int(point[2] // _CELL_KM),
        )

    @staticmethod
    def _ring(cell: tuple[int, int, int], radius: int) -> Iterable[tuple[int, int, int]]:
        cx, cy, cz = cell
        if radius == 0:
            yield cell
            return
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy), abs(dz)) == radius:
                        yield (cx + dx, cy + dy, cz + dz)

    def nearest(
        self,
        latitude: float,
        longitude: float,
        *,
        max_km: float | None = None,
        exclude: str | None = None,
    ) -> tuple[Landmark, float] | None:
        """Ближайший ориентир и расстояние до него по поверхности, в километрах.

        `max_km` обрезает бессмысленные подписи: «120 км от Шексны» человеку
        ничего не говорит, лучше не показать ориентир вовсе.

        `exclude` убирает из поиска само место: город размером с ориентир
        иначе находит себя на нулевом расстоянии, и два одноимённых городка
        остаются неразличимыми.
        """
        if not self._cells:
            return None

        origin = _to_sphere(latitude, longitude)
        cell = self._cell_of(origin)

        best: tuple[Landmark, float] | None = None  # расстояние здесь — хорда
        radius = 0
        while radius <= self._max_radius:
            # Ни одна точка следующего кольца не может лежать ближе этого
            # расстояния — значит найденное уже окончательное.
            if best is not None and (radius - 1) * _CELL_KM > best[1]:
                break
            for neighbour in self._ring(cell, radius):
                for point, landmark in self._cells.get(neighbour, ()):
                    if exclude is not None and landmark.name == exclude:
                        continue
                    chord = math.dist(origin, point)
                    if best is None or chord < best[1]:
                        best = (landmark, chord)
            radius += 1

        if best is None:
            return None
        surface_km = _chord_to_surface(best[1])
        if max_km is not None and surface_km > max_km:
            return None
        return best[0], surface_km


def nearest_landmark(
    landmarks: Sequence[Landmark],
    latitude: float,
    longitude: float,
) -> tuple[Landmark, float] | None:
    """Прямой перебор — для тестов и мелких выборок."""
    if not landmarks:
        return None
    scored = [
        (landmark, distance_km(latitude, longitude, landmark.latitude, landmark.longitude))
        for landmark in landmarks
    ]
    return min(scored, key=lambda item: item[1])
