"""Выбор приза: веса задают шанс, среди равных весов — самый редкий у игрока."""

import random
from types import SimpleNamespace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from astra.wheel.display import discount_label, prize_label, product_display
from astra.wheel.service import choose_prize, free_win_expiry, win_is_available


def _prize(weight: int, code: str = "tarot_wish", discount: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        product_code=code,
        discount_percent=discount,
        weight=weight,
        is_active=True,
    )


def test_heavier_prize_wins_far_more_often() -> None:
    cheap = _prize(90, "tarot_wish", 50)
    expensive = _prize(10, "tarot_relationship", 100)
    rng = random.Random(42)

    counts = {cheap.id: 0, expensive.id: 0}
    for _ in range(2000):
        counts[choose_prize([cheap, expensive], {}, rng).id] += 1

    # 90/10 по весам: дорогой приз редкий, но выпадает.
    assert counts[cheap.id] > counts[expensive.id] * 5
    assert counts[expensive.id] > 0


def test_equal_weights_pick_rarest_for_this_user() -> None:
    a, b, c = _prize(10), _prize(10), _prize(10)
    # b выпадал реже всего именно этому пользователю
    counts = {a.id: 7, b.id: 1, c.id: 4}
    rng = random.Random(0)

    for _ in range(50):
        assert choose_prize([a, b, c], counts, rng).id == b.id


def test_equal_weights_without_history_stay_random() -> None:
    a, b = _prize(10), _prize(10)
    rng = random.Random(1)
    picked = {choose_prize([a, b], {}, rng).id for _ in range(50)}
    assert picked == {a.id, b.id}


def test_tie_break_does_not_cross_weight_groups() -> None:
    # Редкий дорогой приз не должен вытягиваться tie-break'ом из-за нулевой истории
    common = _prize(95)
    rare = _prize(5)
    rng = random.Random(7)
    counts = {common.id: 100, rare.id: 0}

    picks = [choose_prize([common, rare], counts, rng).id for _ in range(500)]
    assert picks.count(common.id) > picks.count(rare.id) * 5


def test_empty_pool_raises() -> None:
    with pytest.raises(ValueError):
        choose_prize([], {})


def test_free_win_expires_at_local_midnight() -> None:
    user = SimpleNamespace(profile=SimpleNamespace(timezone="Europe/Moscow"))
    expiry = free_win_expiry(user, date(2026, 7, 21))
    # Полночь 22-го по Москве = 21:00 UTC 21-го
    assert expiry == datetime(2026, 7, 21, 21, 0, tzinfo=UTC)


def test_paid_win_never_expires_but_activated_is_spent() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    paid = SimpleNamespace(expires_at=None, activated_at=None)
    assert win_is_available(paid, now)

    used = SimpleNamespace(expires_at=None, activated_at=now)
    assert not win_is_available(used, now)


def test_free_win_burns_after_expiry() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    alive = SimpleNamespace(expires_at=datetime(2026, 7, 21, 21, 0, tzinfo=UTC), activated_at=None)
    burned = SimpleNamespace(expires_at=datetime(2026, 7, 20, 21, 0, tzinfo=UTC), activated_at=None)
    assert win_is_available(alive, now)
    assert not win_is_available(burned, now)


def test_prize_labels_are_human_readable() -> None:
    assert product_display("tarot_three_cards") == ("🃏", "Три карты")
    assert product_display("unknown_code")[0] == "🎁"
    assert discount_label(100) == "бесплатно"
    assert discount_label(50) == "−50%"
    assert prize_label("tarot_wish", 50) == "🌟 Загадай желание · −50%"
