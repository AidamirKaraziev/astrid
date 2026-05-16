from datetime import date, datetime, time

from astra.users.getters import calculate_profile_accuracy
from astra.users.models import Profile


def _profile(**kwargs: object) -> Profile:
    defaults = {
        "display_name": "Анна",
        "birth_date": date(1990, 3, 15),
        "birth_time": None,
        "birth_place": None,
        "city": "Москва",
        "timezone": "Europe/Moscow",
    }
    defaults.update(kwargs)
    p = Profile(user_id=__import__("uuid").uuid4(), **defaults)  # type: ignore[arg-type]
    return p


def test_accuracy_level_1() -> None:
    accuracy, _ = calculate_profile_accuracy(_profile())
    assert accuracy == 33


def test_accuracy_level_2() -> None:
    accuracy, _ = calculate_profile_accuracy(
        _profile(birth_time=datetime.combine(date(1990, 3, 15), time(14, 30))),
    )
    assert accuracy == 66


def test_accuracy_level_3() -> None:
    accuracy, hint = calculate_profile_accuracy(
        _profile(
            birth_time=datetime.combine(date(1990, 3, 15), time(14, 30)),
            birth_place="Москва",
        ),
    )
    assert accuracy == 100
    assert "Максимальная" in hint
