"""Отметка активности, серии и учёт вызовов моделей."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.llm.models import LlmPrice
from astra.llm.types import TokenUsage, usage_from_gemini, usage_from_openai
from astra.telegram.activity_middleware import ActivityMiddleware, _actor
from astra.usage.activity import _seconds_until_midnight, dashboard_today, mark_active

_ACTIVITY = "astra.usage.activity"


def _user(timezone: str = "Europe/Moscow"):
    return SimpleNamespace(
        id=uuid4(),
        telegram_id=42,
        profile=SimpleNamespace(timezone=timezone),
        last_active_date=None,
        streak_current=0,
        streak_best=0,
        points=0,
    )


def _redis(first_time: bool = True) -> MagicMock:
    client = MagicMock()
    client.set = AsyncMock(return_value=first_time)
    client.aclose = AsyncMock()
    return client


class TestDashboardDay:
    def test_moscow_day_not_server_day(self):
        """23:30 UTC — в Москве уже завтра, дашборд должен это учитывать."""
        assert dashboard_today(datetime(2026, 7, 29, 23, 30, tzinfo=UTC)) == date(2026, 7, 30)
        assert dashboard_today(datetime(2026, 7, 29, 20, 30, tzinfo=UTC)) == date(2026, 7, 29)

    def test_cache_lives_until_moscow_midnight(self):
        left = _seconds_until_midnight(datetime(2026, 7, 29, 20, 0, tzinfo=UTC))  # 23:00 МСК
        assert 3500 < left <= 3600

    def test_cache_ttl_never_zero(self):
        assert _seconds_until_midnight(datetime(2026, 7, 29, 20, 59, 59, tzinfo=UTC)) >= 60


class TestMarkActive:
    async def test_first_touch_writes_day_and_streak(self):
        user = _user()
        session = AsyncMock()
        with patch(f"{_ACTIVITY}.Redis") as redis:
            redis.from_url.return_value = _redis(first_time=True)
            marked = await mark_active(session, user)

        assert marked is True
        assert user.streak_current == 1
        session.execute.assert_awaited()  # строка дня ушла в базу

    async def test_second_touch_same_day_is_free(self):
        """Сотое нажатие за день не должно ходить в базу вовсе."""
        user = _user()
        session = AsyncMock()
        with patch(f"{_ACTIVITY}.Redis") as redis:
            redis.from_url.return_value = _redis(first_time=False)
            marked = await mark_active(session, user)

        assert marked is False
        session.execute.assert_not_awaited()

    async def test_redis_down_falls_back_to_database(self):
        """Без Redis работаем, только чаще ходим в базу — дубли снимет constraint."""
        user = _user()
        session = AsyncMock()
        with patch(f"{_ACTIVITY}.Redis") as redis:
            redis.from_url.side_effect = RuntimeError("нет соединения")
            marked = await mark_active(session, user)

        assert marked is True
        session.execute.assert_awaited()

    async def test_streak_uses_local_day_dashboard_uses_moscow(self):
        """Серия — по дню человека, дашборд — по Москве; даты расходятся намеренно."""
        user = _user("Asia/Vladivostok")
        session = AsyncMock()
        evening_msk = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)  # 23:00 МСК, 06:00 следующего дня во Владивостоке
        with patch(f"{_ACTIVITY}.Redis") as redis:
            redis.from_url.return_value = _redis()
            await mark_active(session, user, now=evening_msk)

        values = session.execute.await_args.args[0].compile().params
        assert values["day_msk"] == date(2026, 7, 29)
        assert values["day_local"] == date(2026, 7, 30)
        assert user.last_active_date == date(2026, 7, 30)


class TestMiddlewareScope:
    def test_private_message_counts(self):
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=7, is_bot=False),
            chat=SimpleNamespace(type="private"),
        )
        with patch("astra.telegram.activity_middleware.Message", SimpleNamespace):
            assert _actor(event) == (7, True)

    def test_group_message_is_not_user_activity(self):
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=7, is_bot=False),
            chat=SimpleNamespace(type="supergroup"),
        )
        with patch("astra.telegram.activity_middleware.Message", SimpleNamespace):
            assert _actor(event) == (7, False)

    def test_bot_messages_ignored(self):
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=7, is_bot=True),
            chat=SimpleNamespace(type="private"),
        )
        with patch("astra.telegram.activity_middleware.Message", SimpleNamespace):
            assert _actor(event) is None

    async def test_failure_never_breaks_the_update(self):
        """Аналитика не важнее ответа человеку."""
        handler = AsyncMock(return_value="ответ")
        middleware = ActivityMiddleware()
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=7, is_bot=False),
            chat=SimpleNamespace(type="private"),
        )
        with (
            patch("astra.telegram.activity_middleware.Message", SimpleNamespace),
            patch(
                "astra.telegram.activity_middleware.users_crud.get_user_by_telegram_id",
                AsyncMock(side_effect=RuntimeError("база прилегла")),
            ),
        ):
            result = await middleware(handler, event, {"session": AsyncMock()})

        assert result == "ответ"
        handler.assert_awaited_once()


class TestTokenUsage:
    def test_openai_shape(self):
        usage = usage_from_openai({"usage": {"prompt_tokens": 120, "completion_tokens": 900}})
        assert (usage.prompt, usage.completion) == (120, 900)
        assert usage.known

    def test_gemini_shape(self):
        usage = usage_from_gemini(
            {"usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 500}},
        )
        assert (usage.prompt, usage.completion) == (80, 500)

    def test_silent_provider_leaves_hole_not_zero(self):
        """Дырка честнее выдуманного нуля: иначе себестоимость занизится."""
        assert usage_from_openai({}).known is False
        assert usage_from_openai({}).prompt is None


class TestCost:
    def _price(self) -> LlmPrice:
        return LlmPrice(
            model="deepseek-v4-flash",
            input_per_million=Decimal("0.28"),
            output_per_million=Decimal("0.42"),
        )

    def test_cost_math(self):
        cost = self._price().cost_usd(3200, 1500)
        assert cost == Decimal("0.001526")

    def test_no_tokens_no_cost(self):
        assert self._price().cost_usd(None, None) is None

    def test_partial_tokens_still_counted(self):
        assert self._price().cost_usd(1_000_000, None) == Decimal("0.280000")
