"""Очередь проблем: что попадает в список, что можно чинить и чем."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.admin import queue
from astra.admin.queue import Problem, Target, Trouble, refund, retry, summarize
from astra.admin.render_queue import queue_page
from astra.admin.service import AdminError

_QUEUE = "astra.admin.queue"


def _problem(**overrides) -> Problem:
    data = {
        "trouble": Trouble.STUCK,
        "target": Target.TAROT,
        "entity_id": uuid.uuid4(),
        "product": "Таро · wish",
        "who": "@lunayeva",
        "telegram_id": 481923746,
        "amount": 150,
        "status": "generating",
        "since": datetime.now(UTC) - timedelta(hours=2),
        "reason": "воркер не ответил",
        "can_retry": True,
        "can_refund": True,
    }
    return Problem(**{**data, **overrides})


class TestAge:
    def test_human_readable(self):
        now = datetime.now(UTC)
        assert _problem(since=now - timedelta(minutes=12)).age_human == "12 мин"
        assert _problem(since=now - timedelta(hours=3)).age_human == "3 ч"
        assert _problem(since=now - timedelta(days=2)).age_human == "2 дн"


class TestSummary:
    def test_counts_money_and_oldest(self):
        problems = [
            _problem(amount=150, since=datetime.now(UTC) - timedelta(hours=5)),
            _problem(amount=200, trouble=Trouble.FAILED),
            _problem(amount=None, trouble=Trouble.FAILED, can_refund=False),
        ]
        summary = summarize(problems)
        assert summary.total == 3
        assert summary.stuck == 1
        assert summary.money_at_risk == 350
        assert summary.oldest == "5 ч"

    def test_empty(self):
        assert summarize([]).total == 0
        assert summarize([]).oldest == "—"


class TestRetry:
    async def test_tarot_goes_back_to_queue(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), spread_type="wish"))
        with patch(f"{_QUEUE}.publish_tarot_reading_generate", AsyncMock()) as publish:
            message = await retry(session, Target.TAROT, uuid.uuid4())
        publish.assert_awaited_once()
        assert "снова в очереди" in message

    async def test_ask_goes_back_to_queue(self):
        session = AsyncMock()
        session.get = AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4(), question_key="love_kids"),
        )
        with patch(f"{_QUEUE}.publish_ask_answer_generate", AsyncMock()) as publish:
            await retry(session, Target.ASK, uuid.uuid4())
        publish.assert_awaited_once()

    async def test_missing_entity_is_admin_error(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        with pytest.raises(AdminError):
            await retry(session, Target.TAROT, uuid.uuid4())

    async def test_orphan_payment_cannot_be_retried(self):
        with pytest.raises(AdminError):
            await retry(AsyncMock(), Target.PAYMENT, uuid.uuid4())


class TestRefund:
    async def test_tarot_refund_marks_payment(self):
        reading = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        payment = SimpleNamespace(
            provider_charge_id="charge_1", amount=150, status="completed",
        )
        session = AsyncMock()
        session.get = AsyncMock(side_effect=[reading, SimpleNamespace(telegram_id=42)])
        with (
            patch(f"{_QUEUE}.refund_star_payment_api", AsyncMock()) as api,
            patch(
                f"{_QUEUE}.payments_crud.get_completed_payment_for_reading",
                AsyncMock(return_value=payment),
            ),
            patch(f"{_QUEUE}.payments_crud.get_payment_by_charge", AsyncMock(return_value=payment)),
            patch(f"{_QUEUE}.payments_crud.mark_payment_refunded", AsyncMock()) as mark,
        ):
            message = await refund(session, Target.TAROT, uuid.uuid4())
        api.assert_awaited_once_with(42, "charge_1")
        mark.assert_awaited_once()
        assert "150 ⭐" in message

    async def test_ask_refund_is_idempotent(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=SimpleNamespace(refunded=True, charge_id="c"))
        with pytest.raises(AdminError, match="уже возвращены"):
            await refund(session, Target.ASK, uuid.uuid4())

    async def test_telegram_error_becomes_readable(self):
        reading = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        session = AsyncMock()
        session.get = AsyncMock(side_effect=[reading, SimpleNamespace(telegram_id=42)])
        with (
            patch(
                f"{_QUEUE}.refund_star_payment_api",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch(
                f"{_QUEUE}.payments_crud.get_completed_payment_for_reading",
                AsyncMock(return_value=SimpleNamespace(provider_charge_id="c", amount=1)),
            ),
        ):
            with pytest.raises(AdminError, match="Telegram не принял возврат"):
                await refund(session, Target.TAROT, uuid.uuid4())

    async def test_free_product_has_nothing_to_refund(self):
        with pytest.raises(AdminError):
            await refund(AsyncMock(), Target.NATAL, uuid.uuid4())

    async def test_payment_without_order_refunds_by_charge(self):
        payment = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            provider_charge_id="charge_2",
            amount=50,
            status="completed",
        )
        session = AsyncMock()
        session.get = AsyncMock(side_effect=[payment, SimpleNamespace(telegram_id=7)])
        with (
            patch(f"{_QUEUE}.refund_star_payment_api", AsyncMock()) as api,
            patch(f"{_QUEUE}.payments_crud.get_payment_by_charge", AsyncMock(return_value=payment)),
            patch(f"{_QUEUE}.payments_crud.mark_payment_refunded", AsyncMock()),
        ):
            await refund(session, Target.PAYMENT, uuid.uuid4())
        api.assert_awaited_once_with(7, "charge_2")


class TestStuckWindow:
    async def test_recent_in_flight_is_not_a_problem(self):
        """Заказ, который в работе минуту, — это нормальная жизнь, а не авария."""
        fresh = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status="generating",
            updated_at=datetime.now(UTC) - timedelta(minutes=1),
            spread_type="wish",
            price_stars=150,
            failure_reason=None,
        )
        old = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status="generating",
            updated_at=datetime.now(UTC) - timedelta(minutes=queue.STUCK_AFTER_MINUTES + 5),
            spread_type="year",
            price_stars=300,
            failure_reason=None,
        )
        user = SimpleNamespace(username="lunayeva", telegram_id=1)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(fresh, user), (old, user)])),
        )
        problems = await queue._tarot_problems(session)
        assert [p.product for p in problems] == ["Таро · year"]
        assert problems[0].trouble is Trouble.STUCK


class TestRender:
    def test_shows_rows_and_actions(self):
        html = queue_page([_problem()], summarize([_problem()]))
        assert "Таро · wish" in html
        assert "Повторить" in html
        assert "/refund" in html
        assert "confirm(" in html  # возврат спрашивает подтверждение

    def test_empty_queue_is_good_news(self):
        html = queue_page([], summarize([]))
        assert "Чисто" in html
        assert "Повторить" not in html

    def test_free_product_has_no_refund_button(self):
        problem = _problem(amount=None, can_refund=False, target=Target.NATAL, product="Натал")
        html = queue_page([problem], summarize([problem]))
        assert "/refund" not in html
        assert "бесплатно" in html

    def test_reason_is_escaped(self):
        problem = _problem(reason="<script>alert(1)</script>")
        html = queue_page([problem], summarize([problem]))
        assert "<script>alert(1)</script>" not in html
