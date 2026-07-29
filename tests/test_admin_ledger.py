"""Лента событий: фильтры, склейка источников и постраничный вывод."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from astra.admin.ledger import (
    PAGE_SIZE,
    Event,
    Filters,
    Kind,
    Totals,
    collect,
)
from astra.admin.render_ledger import _toggle, ledger_page

_NOW = datetime.now(UTC)


def _event(**overrides) -> Event:
    data = {
        "at": _NOW,
        "kind": Kind.PAYMENT,
        "product": "tarot_wish",
        "title": "Расклад на желание",
        "who": "@lunayeva",
        "amount": 150,
        "status": "оплачен",
        "note": "",
    }
    return Event(**{**data, **overrides})


class TestFilters:
    def test_periods(self):
        assert Filters(period="all").since is None
        assert Filters(period="today").since.hour == 0
        week = Filters(period="7").since
        assert timedelta(days=6, hours=23) < _NOW - week < timedelta(days=7, hours=1)

    def test_empty_selection_means_everything(self):
        empty = Filters()
        assert empty.wants(Kind.SPIN, "wheel_spin")
        assert empty.wants(Kind.PAYMENT, "tarot_wish")

    def test_product_toggle_excludes_the_rest(self):
        """Заказчик просил: любой товар выключается из выборки одним кликом."""
        only_tarot = Filters(products={"tarot_wish"})
        assert only_tarot.wants(Kind.PAYMENT, "tarot_wish")
        assert not only_tarot.wants(Kind.SPIN, "wheel_spin")

    def test_kind_filter(self):
        money_only = Filters(kinds={"payment", "refund"})
        assert money_only.wants(Kind.PAYMENT, "tarot_wish")
        assert not money_only.wants(Kind.DELIVERY, "tarot_wish")


class TestToggle:
    def test_click_adds_and_removes(self):
        assert _toggle(set(), "tarot_wish") == {"tarot_wish"}
        assert _toggle({"tarot_wish"}, "tarot_wish") == set()
        assert _toggle({"a"}, "b") == {"a", "b"}


def _session(payments=(), tarot=(), ask=(), natal=(), compat=(), daily=(), spins=()):
    """Восемь запросов подряд: каталог, платежи, четыре вида заказов, дневные, колесо."""
    results = [
        MagicMock(all=MagicMock(return_value=[("tarot_wish", "Расклад на желание")])),
        MagicMock(all=MagicMock(return_value=list(payments))),
        MagicMock(all=MagicMock(return_value=list(tarot))),
        MagicMock(all=MagicMock(return_value=list(ask))),
        MagicMock(all=MagicMock(return_value=list(natal))),
        MagicMock(all=MagicMock(return_value=list(compat))),
        MagicMock(all=MagicMock(return_value=list(daily))),
        MagicMock(all=MagicMock(return_value=list(spins))),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    return session


def _user(username="lunayeva"):
    return SimpleNamespace(id=uuid4(), username=username, telegram_id=1)


class TestCollect:
    async def test_refunded_payment_gives_two_rows(self):
        """Оплата и возврат — разные события, иначе не видно, когда деньги вернулись."""
        payment = SimpleNamespace(
            product_code="tarot_wish",
            amount=150,
            discount_percent=0,
            status="refunded",
            created_at=_NOW - timedelta(hours=2),
            refunded_at=_NOW - timedelta(hours=1),
            user_id=uuid4(),
        )
        events, totals, total = await collect(
            _session(payments=[(payment, _user())]), Filters(period="all"),
        )
        assert [event.kind for event in events] == [Kind.REFUND, Kind.PAYMENT]
        assert totals.money_in == 150
        assert totals.money_back == 150
        assert totals.net == 0
        assert total == 2

    async def test_abandoned_draft_is_visible(self):
        """Человек дошёл до оплаты и передумал — это видно в ленте."""
        draft = SimpleNamespace(
            spread_type="wish",
            status="pending_payment",
            price_stars=None,
            created_at=_NOW,
            updated_at=_NOW,
            user_id=uuid4(),
        )
        events, totals, _ = await collect(
            _session(tarot=[(draft, _user())]), Filters(period="all"),
        )
        assert events[0].kind is Kind.DRAFT
        assert events[0].status == "не оплачен"
        assert totals.deliveries == 0

    async def test_free_delivery_counted_separately(self):
        usage = SimpleNamespace(action="day_card", created_at=_NOW, user_id=uuid4())
        _, totals, _ = await collect(
            _session(daily=[(usage, _user())]), Filters(period="all"),
        )
        assert totals.deliveries == 1
        assert totals.free_deliveries == 1
        assert totals.money_in == 0

    async def test_spin_shows_prize_fate(self):
        win = SimpleNamespace(
            product_code="tarot_wish",
            discount_percent=100,
            activated_at=None,
            expires_at=_NOW - timedelta(hours=1),
            created_at=_NOW,
            user_id=uuid4(),
        )
        events, _, _ = await collect(
            _session(spins=[(win, _user())]), Filters(period="all"),
        )
        assert events[0].kind is Kind.SPIN
        assert events[0].status == "приз сгорел"
        assert "−100%" in events[0].note

    async def test_filter_by_person(self):
        payment = SimpleNamespace(
            product_code="tarot_wish", amount=50, discount_percent=0, status="completed",
            created_at=_NOW, refunded_at=None, user_id=uuid4(),
        )
        events, _, _ = await collect(
            _session(payments=[(payment, _user("kirill"))]),
            Filters(period="all", query="@lunayeva"),
        )
        assert events == []


class TestPaging:
    async def test_second_page_offsets(self):
        payments = [
            (
                SimpleNamespace(
                    product_code="tarot_wish", amount=index, discount_percent=0,
                    status="completed", created_at=_NOW - timedelta(minutes=index),
                    refunded_at=None, user_id=uuid4(),
                ),
                _user(),
            )
            for index in range(1, PAGE_SIZE + 11)
        ]
        page_two, totals, total = await collect(
            _session(payments=payments), Filters(period="all", page=2),
        )
        assert total == PAGE_SIZE + 10
        assert len(page_two) == 10
        assert totals.events == PAGE_SIZE + 10  # итоги считаются по всей выборке


class TestRender:
    def _products(self):
        return [("tarot_wish", "Расклад на желание"), ("wheel_spin", "Вращение колеса")]

    def test_chips_reflect_selection(self):
        filters = Filters(period="7", products={"tarot_wish"})
        html = ledger_page([_event()], Totals(events=1, money_in=150), filters, self._products())
        assert "Расклад на желание" in html
        # клик по второму товару добавит его к выбранному (запятая в URL кодируется)
        assert "products=tarot_wish%2Cwheel_spin" in html
        assert "любой товар выключается кликом" in html

    def test_pager_appears_only_when_needed(self):
        filters = Filters()
        small = ledger_page([_event()], Totals(events=1), filters, self._products())
        assert "вперёд" not in small

        big = ledger_page([_event()], Totals(events=PAGE_SIZE * 3), filters, self._products())
        assert "вперёд" in big
        assert "1 из 3" in big

    def test_empty_selection_says_so(self):
        html = ledger_page([], Totals(), Filters(), self._products())
        assert "ничего не происходило" in html

    def test_free_row_marked(self):
        html = ledger_page(
            [_event(amount=None, kind=Kind.DELIVERY, status="выдано")],
            Totals(deliveries=1, free_deliveries=1),
            Filters(),
            self._products(),
        )
        assert "бесплатно" in html
