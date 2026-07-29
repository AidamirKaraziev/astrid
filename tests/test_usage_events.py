"""Журнал использования и серия дней: раньше серию двигал только /start."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.services.points_service import register_daily_activity
from astra.usage import UsageKind, record_usage
from astra.users.local_time import local_today

_SERVICE = "astra.usage.service"


def _user(timezone: str = "Europe/Moscow", **overrides):
    data = {
        "id": uuid4(),
        "profile": SimpleNamespace(timezone=timezone),
        "last_active_date": None,
        "streak_current": 0,
        "streak_best": 0,
        "points": 0,
    }
    return SimpleNamespace(**{**data, **overrides})


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


class TestLocalDay:
    def test_timezone_from_profile(self):
        assert local_today(_user("Pacific/Kiritimati")) >= local_today(_user("Pacific/Niue"))

    def test_user_without_profile_does_not_crash(self):
        """До онбординга профиля нет — серия всё равно должна начисляться."""
        assert local_today(_user(profile=None)) is not None

    def test_broken_timezone_falls_back(self):
        assert local_today(_user("Сатурн/Кольцо")) is not None


class TestRecordUsage:
    async def test_writes_event_and_starts_streak(self):
        user = _user()
        session = _session()
        await record_usage(session, user, action="day_card", kind=UsageKind.FORECAST)

        event = session.add.call_args_list[0].args[0]
        assert event.action == "day_card"
        assert event.kind == "forecast"
        assert event.is_paid is False
        assert event.local_date == local_today(user)
        assert user.streak_current == 1

    async def test_paid_flag_kept(self):
        user = _user()
        session = _session()
        await record_usage(
            session, user, action="tarot_wish", kind=UsageKind.TAROT, is_paid=True,
        )
        assert session.add.call_args_list[0].args[0].is_paid is True

    async def test_second_use_same_day_adds_event_but_not_points(self):
        """Кнопок можно нажать много — очки за день одни."""
        user = _user()
        session = _session()
        await record_usage(session, user, action="day_card", kind=UsageKind.FORECAST)
        points_after_first = user.points
        await record_usage(session, user, action="tarot_daily", kind=UsageKind.TAROT)

        events = [call.args[0] for call in session.add.call_args_list]
        assert [e.action for e in events if hasattr(e, "action")] == ["day_card", "tarot_daily"]
        assert user.points == points_after_first
        assert user.streak_current == 1


class TestStreak:
    async def test_next_day_extends(self):
        today = date(2026, 7, 29)
        user = _user(last_active_date=today - timedelta(days=1), streak_current=4, streak_best=4)
        _, streak = await register_daily_activity(_session(), user, activity_date=today)
        assert streak == 5
        assert user.streak_best == 5

    async def test_gap_resets(self):
        today = date(2026, 7, 29)
        user = _user(last_active_date=today - timedelta(days=3), streak_current=9, streak_best=9)
        _, streak = await register_daily_activity(_session(), user, activity_date=today)
        assert streak == 1
        assert user.streak_best == 9  # рекорд не теряется

    async def test_same_day_is_noop(self):
        today = date(2026, 7, 29)
        user = _user(last_active_date=today, streak_current=3)
        points, streak = await register_daily_activity(_session(), user, activity_date=today)
        assert (points, streak) == (0, 3)

    async def test_uses_user_timezone_not_server_date(self):
        """Серия должна переключаться в полночь человека, а не сервера."""
        user = _user("Pacific/Kiritimati")
        session = _session()
        with patch(f"{_SERVICE}.local_today", return_value=date(2026, 7, 30)) as clock:
            await record_usage(session, user, action="day_card", kind=UsageKind.FORECAST)
        clock.assert_called_once_with(user)
        assert user.last_active_date == date(2026, 7, 30)
