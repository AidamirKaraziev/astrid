"""Метрики: арифметика витрин и разбивка серий по группам."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from astra.admin.metrics import (
    STREAK_BUCKETS,
    Audience,
    FunnelStep,
    Money,
    ProductUsage,
    Referrals,
    Repeat,
    Wheel,
    streak_buckets,
)


class TestMoney:
    def test_average_check(self):
        assert Money(revenue=4830, payments=41).average_check == 118

    def test_no_payments_no_division(self):
        assert Money().average_check == 0


class TestRepeat:
    def test_share_and_per_buyer(self):
        repeat = Repeat(paying_users=8, repeat_users=2, revenue_total=1600)
        assert repeat.repeat_share == 25.0
        assert repeat.revenue_per_buyer == 200

    def test_empty(self):
        assert Repeat().repeat_share == 0.0
        assert Repeat().revenue_per_buyer == 0


class TestAudience:
    def test_stickiness_is_dau_over_mau(self):
        assert Audience(dau=100, wau=400, mau=1000).stickiness == 10.0

    def test_no_mau(self):
        assert Audience().stickiness == 0.0


class TestFunnel:
    def test_share_of_start(self):
        assert FunnelStep("Оплатили", 604).share(3412) == 17.7
        assert FunnelStep("Оплатили", 0).share(0) == 0.0


class TestProductUsage:
    def test_free_is_total_minus_paid(self):
        product = ProductUsage("tarot_wish", "Расклад", uses=10, users=6, paid_uses=4)
        assert product.free_uses == 6


class TestWheel:
    def test_activation_share(self):
        wheel = Wheel(wins_total=8, wins_activated=2)
        assert wheel.activation_share == 25.0

    def test_spins_sum(self):
        assert Wheel(spins_free=4, spins_paid=3).spins == 7


class TestReferrals:
    def test_conversions_compared(self):
        ref = Referrals(invited=20, invited_buyers=6, organic=100, organic_buyers=10)
        assert ref.invited_conversion == 30.0
        assert ref.organic_conversion == 10.0


class TestStreakBuckets:
    """Заказчик просил именно такую разбивку: 1..7, затем 14 и 30."""

    async def _buckets(self, distribution: dict[int, int]):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=list(distribution.items()))),
        )
        return await streak_buckets(session)

    async def test_groups_match_requested_edges(self):
        buckets = await self._buckets({})
        assert [label for label, _ in buckets] == [
            "1", "2", "3", "4", "5", "6", "7–13", "14–29", "30+",
        ]
        assert STREAK_BUCKETS == (1, 2, 3, 4, 5, 6, 7, 14, 30)

    async def test_single_days_counted_exactly(self):
        buckets = dict(await self._buckets({1: 40, 2: 12, 5: 3}))
        assert buckets["1"] == 40
        assert buckets["2"] == 12
        assert buckets["5"] == 3
        assert buckets["3"] == 0

    async def test_ranges_and_tail(self):
        buckets = dict(await self._buckets({7: 2, 9: 1, 13: 1, 14: 3, 29: 1, 30: 2, 91: 1}))
        assert buckets["7–13"] == 4
        assert buckets["14–29"] == 4
        assert buckets["30+"] == 3


class TestDates:
    async def test_revenue_days_fills_gaps_with_zero(self):
        """Пустой день должен быть нулевым столбиком, а не пропуском."""
        from astra.admin import metrics

        rows = [(date(2026, 7, 29), 1270)]
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=rows)),
        )
        with patch("astra.admin.metrics.datetime") as clock:
            clock.now.return_value.date.return_value = date(2026, 7, 29)
            days = await metrics.revenue_by_day(session, 7)
        assert len(days) == 7
        assert days[-1] == (date(2026, 7, 29), 1270)
        assert all(value == 0 for _, value in days[:-1])
