"""Ряды дашборда: календарная нарезка, уникальные люди, два ряда генераций."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from astra.admin.render_timeline import charts, grain_switch
from astra.admin.timeline import (
    DEPTH,
    Bucket,
    Grain,
    LlmSpend,
    Timeline,
    _fold,
    active_people,
    buckets,
)

_TODAY = date(2026, 7, 29)  # среда


class TestBuckets:
    def test_days_are_thirty_and_end_today(self):
        items = buckets(Grain.DAY, _TODAY)
        assert len(items) == DEPTH[Grain.DAY] == 30
        assert items[-1].start == _TODAY
        assert items[0].start == date(2026, 6, 30)

    def test_weeks_start_on_monday(self):
        items = buckets(Grain.WEEK, _TODAY)
        assert len(items) == 12
        assert items[-1].start == date(2026, 7, 27)  # понедельник этой недели
        assert all(item.start.weekday() == 0 for item in items)

    def test_months_start_on_first_and_cover_year(self):
        items = buckets(Grain.MONTH, _TODAY)
        assert len(items) == 12
        assert items[-1].start == date(2026, 7, 1)
        assert items[0].start == date(2025, 8, 1)
        assert all(item.start.day == 1 for item in items)

    def test_only_last_period_is_current(self):
        """Текущий период неполный — на графике он приглушён, а не читается как обвал."""
        for grain in Grain:
            items = buckets(grain, _TODAY)
            assert [item.current for item in items].count(True) == 1
            assert items[-1].current


class TestFold:
    def test_days_fold_into_weeks(self):
        items = buckets(Grain.WEEK, _TODAY)
        rows = [(date(2026, 7, 27), 5), (date(2026, 7, 28), 7), (date(2026, 7, 20), 3)]
        folded = _fold(rows, Grain.WEEK, items)
        assert folded[-1] == 12  # 27-е и 28-е — одна неделя
        assert folded[-2] == 3

    def test_days_outside_range_ignored(self):
        items = buckets(Grain.DAY, _TODAY)
        assert sum(_fold([(date(2020, 1, 1), 99)], Grain.DAY, items)) == 0


class TestActivePeople:
    async def _people(self, rows, grain: Grain):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=rows)),
        )
        return await active_people(session, grain, buckets(grain, _TODAY))

    async def test_same_person_counted_once_per_period(self):
        """Человек, заходивший три дня подряд, в неделе — единица."""
        someone = uuid4()
        rows = [
            (date(2026, 7, 27), someone),
            (date(2026, 7, 28), someone),
            (date(2026, 7, 29), someone),
        ]
        assert (await self._people(rows, Grain.WEEK))[-1] == 1
        assert (await self._people(rows, Grain.DAY))[-3:] == [1, 1, 1]

    async def test_month_is_not_the_sum_of_days(self):
        first, second = uuid4(), uuid4()
        rows = [
            (date(2026, 7, 3), first),
            (date(2026, 7, 4), first),
            (date(2026, 7, 5), second),
        ]
        days = await self._people(rows, Grain.DAY)
        month = await self._people(rows, Grain.MONTH)
        assert sum(days) == 3
        assert month[-1] == 2


def _timeline() -> Timeline:
    items = [
        Bucket(date(2026, 7, 27), "27.07"),
        Bucket(date(2026, 7, 28), "28.07"),
        Bucket(date(2026, 7, 29), "29.07", current=True),
    ]
    return Timeline(
        grain=Grain.DAY,
        buckets=items,
        people=[5, 7, 3],
        products=[10, 12, 4],
        calls=[24, 30, 9],
        money=[300, 450, 120],
    )


class TestRender:
    def test_three_charts_with_two_series_for_generations(self):
        html = charts(_timeline(), LlmSpend(calls=63, cost_usd=1.42))
        assert "Активные люди" in html
        assert "Генерации" in html
        assert "Выручка" in html
        assert "выдано продуктов" in html and "вызовов модели" in html
        assert "$1.42" in html

    def test_calls_per_product_shown(self):
        html = charts(_timeline(), LlmSpend())
        assert "2.4 вызова на продукт" in html  # 63 вызова на 26 продуктов

    def test_current_period_marked(self):
        html = charts(_timeline(), LlmSpend())
        assert "now" in html
        assert "период ещё идёт" in html

    def test_switch_marks_active_grain(self):
        html = grain_switch(Grain.MONTH)
        assert 'href="/admin/metrics?grain=month" class="on"' in html
        assert 'href="/admin/metrics?grain=day" class=""' in html

    def test_empty_data_does_not_divide_by_zero(self):
        empty = Timeline(Grain.DAY, [Bucket(_TODAY, "29.07", True)], [0], [0], [0], [0])
        html = charts(empty, LlmSpend())
        assert "Активные люди" in html
