"""Ежедневная сводка: текст и расписание отправки."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from astra.admin.daily_report import _change, _times, build_daily_report
from astra.core.config import Settings
from astra.notifications.scheduler import _last_report_sent, send_daily_report_if_due

_REPORT = "astra.admin.daily_report"


def _settings(**overrides) -> Settings:
    base = {
        "telegram_admin_group_id": -1001234567890,
        "admin_report_enabled": True,
        "admin_report_hour": 10,
        "admin_report_timezone": "Europe/Moscow",
    }
    return Settings(**{**base, **overrides})


def _moscow(hour: int, minute: int = 0, day: int = 29) -> datetime:
    """Момент в UTC, который в Москве даёт нужное время (МСК = UTC+3)."""
    return datetime(2026, 7, day, hour - 3, minute, tzinfo=UTC)


class TestWording:
    def test_times_plural(self):
        assert [_times(n) for n in (1, 2, 5, 11, 21, 22)] == [
            "1 раз", "2 раза", "5 раз", "11 раз", "21 раз", "22 раза",
        ]

    def test_change_marks_growth_and_first_data(self):
        assert _change(120, 100) == " (+20%)"
        assert _change(80, 100) == " (-20%)"
        assert _change(100, 100) == " (как вчера)"
        assert _change(5, 0) == " (первые)"
        assert _change(0, 0) == ""


class TestReportText:
    async def _build(self, *, usage, failed=(0, 0), money=(430, 4, 3)):
        audience = SimpleNamespace(dau=12, wau=30, mau=48, stickiness=25.0)
        with (
            patch(f"{_REPORT}._day_money", AsyncMock(side_effect=[money, (330, 3, 3)])),
            patch(f"{_REPORT}._day_signups", AsyncMock(side_effect=[7, 5])),
            patch(f"{_REPORT}._day_usage", AsyncMock(return_value=usage)),
            patch(f"{_REPORT}.metrics.audience", AsyncMock(return_value=audience)),
            patch(f"{_REPORT}.metrics.failed_share", AsyncMock(return_value=failed)),
            patch(f"{_REPORT}.metrics.product_usage", AsyncMock(return_value=[])),
        ):
            return await build_daily_report(AsyncMock(), date(2026, 7, 28))

    async def test_money_people_and_products(self):
        text = await self._build(usage=[("day_card", 14, 6), ("tarot_wish", 3, 3)])
        assert "Astra за 28.07" in text
        assert "430 ⭐" in text and "(+30%)" in text
        assert "Новых людей: <b>7</b> (+40%)" in text
        assert "day_card — 14 раз, 6 чел." in text
        assert "липкость 25.0%" in text

    async def test_quiet_day_says_so(self):
        text = await self._build(usage=[], money=(0, 0, 0))
        assert "Продуктами вчера не пользовались" in text

    async def test_failures_are_flagged(self):
        text = await self._build(usage=[("day_card", 1, 1)], failed=(2, 16))
        assert "Упало разборов" in text and "загляни в очередь" in text


class TestSchedule:
    def setup_method(self):
        _last_report_sent.clear()

    async def test_sends_once_at_configured_hour(self):
        send = AsyncMock()
        with patch(f"{_REPORT}.build_daily_report", AsyncMock(return_value="сводка")):
            first = await send_daily_report_if_due(
                MagicMock(), send, _settings(), now_utc=_moscow(10),
            )
            second = await send_daily_report_if_due(
                MagicMock(), send, _settings(), now_utc=_moscow(10),
            )
        assert (first, second) == (True, False)
        send.assert_awaited_once()
        assert send.await_args.args[0] == -1001234567890

    async def test_silent_at_other_hours(self):
        send = AsyncMock()
        assert not await send_daily_report_if_due(
            MagicMock(), send, _settings(), now_utc=_moscow(9, 59),
        )
        send.assert_not_awaited()

    async def test_next_day_sends_again(self):
        send = AsyncMock()
        with patch(f"{_REPORT}.build_daily_report", AsyncMock(return_value="сводка")):
            await send_daily_report_if_due(MagicMock(), send, _settings(), now_utc=_moscow(10, day=29))
            await send_daily_report_if_due(MagicMock(), send, _settings(), now_utc=_moscow(10, day=30))
        assert send.await_count == 2

    async def test_disabled_or_no_group_is_noop(self):
        send = AsyncMock()
        assert not await send_daily_report_if_due(
            MagicMock(), send, _settings(admin_report_enabled=False), now_utc=_moscow(10),
        )
        assert not await send_daily_report_if_due(
            MagicMock(), send, _settings(telegram_admin_group_id=0), now_utc=_moscow(10),
        )
        send.assert_not_awaited()
