"""Ориентир для тёзок: «Горка · 12 км от Устюжны».

Сетка существует ради скорости, но обязана давать тот же ответ, что и
честный перебор. Если разойдётся — человек увидит подпись от чужого города
и выберет не своё место рождения.
"""

from __future__ import annotations

import random

import pytest

from astra.places.nearest import Landmark, LandmarkIndex, distance_km, nearest_landmark

MOSCOW = (55.7558, 37.6173)
VOLOGDA = (59.2187, 39.8886)
VLADIVOSTOK = (43.1167, 131.9)


class TestDistance:
    def test_known_distance_moscow_vologda(self) -> None:
        # Справочное расстояние по прямой — около 400 км.
        assert 390 < distance_km(*MOSCOW, *VOLOGDA) < 420

    def test_zero_for_same_point(self) -> None:
        assert distance_km(*MOSCOW, *MOSCOW) == pytest.approx(0.0)

    def test_symmetric(self) -> None:
        there = distance_km(*MOSCOW, *VLADIVOSTOK)
        back = distance_km(*VLADIVOSTOK, *MOSCOW)
        assert there == pytest.approx(back)


class TestLandmarkIndex:
    def test_finds_the_obvious_neighbour(self) -> None:
        index = LandmarkIndex(
            [
                Landmark("Вологда", *VOLOGDA),
                Landmark("Москва", *MOSCOW),
                Landmark("Владивосток", *VLADIVOSTOK),
            ],
        )
        found = index.nearest(59.3, 39.9)
        assert found is not None
        assert found[0].name == "Вологда"
        assert found[1] < 20

    def test_matches_brute_force_on_random_points(self) -> None:
        """Главная гарантия: сетка не срезает углы.

        Тысяча случайных точек по всей стране — на каждой ответ сетки должен
        совпасть с прямым перебором.
        """
        rng = random.Random(20260806)
        landmarks = [
            Landmark(
                f"город-{i}",
                rng.uniform(42.0, 68.0),
                rng.uniform(20.0, 170.0),
            )
            for i in range(300)
        ]
        index = LandmarkIndex(landmarks)

        for _ in range(1000):
            lat = rng.uniform(42.0, 68.0)
            lon = rng.uniform(20.0, 170.0)
            fast = index.nearest(lat, lon)
            slow = nearest_landmark(landmarks, lat, lon)
            assert fast is not None
            assert slow is not None
            assert fast[1] == pytest.approx(slow[1], abs=1e-6), (
                f"сетка промахнулась на ({lat:.3f}, {lon:.3f}): "
                f"{fast[0].name} вместо {slow[0].name}"
            )

    def test_longitude_compression_near_the_pole(self) -> None:
        """На широте Мурманска градус долготы — сорок километров, не сто одиннадцать.

        Без поправки на широту сетка считала бы северные города дальше, чем
        они есть, и выбирала бы ориентир южнее.
        """
        murmansk = (68.97, 33.08)
        index = LandmarkIndex(
            [
                Landmark("рядом по долготе", 68.97, 34.5),
                Landmark("рядом по широте", 69.9, 33.08),
            ],
        )
        found = index.nearest(*murmansk)
        assert found is not None
        assert found[0].name == "рядом по долготе"

    def test_max_km_hides_useless_landmark(self) -> None:
        """«120 км от Шексны» человеку ничего не говорит — лучше без подписи."""
        index = LandmarkIndex([Landmark("Шексна", 59.2, 38.5)])
        assert index.nearest(50.0, 30.0, max_km=100) is None
        assert index.nearest(59.21, 38.51, max_km=100) is not None

    def test_empty_index(self) -> None:
        assert LandmarkIndex([]).nearest(*MOSCOW) is None

    def test_landmark_itself_is_zero_away(self) -> None:
        index = LandmarkIndex([Landmark("Москва", *MOSCOW)])
        found = index.nearest(*MOSCOW)
        assert found is not None
        assert found[1] == pytest.approx(0.0, abs=0.001)
