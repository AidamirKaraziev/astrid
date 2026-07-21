"""Карта дня: промпт-продукт, сервис прогноза и утренняя доставка."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.llm.prompts import day_card as prompt
from astra.messaging.schemas import TaskMessage, TaskType
from astra.services import day_card_service
from astra.tarot.deck import card_by_id
from astra.tarot.models import CONTEXT_DAY_CARD
from astra.workers import handlers

_CARD = card_by_id("major_07")  # Колесница
_TARGET = date(2026, 7, 22)

_CONTEXT_V2 = {
    "schema_version": 2,
    "date": _TARGET.isoformat(),
    "moon": {"sign": "Рак", "phase": "растущая"},
    "conflict": {"side_a": "сказать прямо", "side_b": "промолчать"},
}


def _reading(**overrides) -> prompt.DayCardReading:
    data = {
        "essence": "День, когда всё решает то, как ты держишь руль.",
        "affairs": "Дела двигаются, пока ты ведёшь их сам, а не ждёшь отмашки. "
        "Не бери третью задачу, пока первая не доехала.",
        "relations": "Разговор получится, если сказать главное один раз и спокойно. "
        "Дожимать сегодня — значит потерять то, что уже услышали.",
        "energy": "Силы есть до вечера, но они уходят на удержание, а не на рывок. "
        "После шести лучше не начинать ничего нового.",
        "step": "Напиши тому, кто ждёт от тебя ответа.",
    }
    data.update(overrides)
    return prompt.DayCardReading(**data)


class TestPrompt:
    def test_valid_reading_passes(self) -> None:
        assert prompt.validate(_reading()) is None

    def test_essence_must_read_at_a_glance(self) -> None:
        assert prompt.validate(_reading(essence="Ок.")) == "invalid_essence"
        assert prompt.validate(_reading(essence="Сегодня " * 30)) == "invalid_essence"

    def test_short_sphere_rejected(self) -> None:
        assert prompt.validate(_reading(affairs="Всё норм.")) == "field_affairs_too_short"

    def test_step_must_stay_one_action(self) -> None:
        assert prompt.validate(_reading(step="Будь.")) == "invalid_step"

    def test_parse_accepts_fenced_json(self) -> None:
        raw = "```json\n" + _reading().model_dump_json() + "\n```"
        data = prompt.parse(raw)
        assert data is not None
        assert data.step.startswith("Напиши")

    def test_parse_rejects_garbage(self) -> None:
        assert prompt.parse("карты молчат") is None

    def test_render_puts_essence_and_spheres_in_order(self) -> None:
        text = prompt.render(_CARD, _TARGET, _CONTEXT_V2, _reading())
        assert "Колесница · 22 июля" in text
        assert "🌙 Луна в Раке, растущая" in text
        assert text.index("Суть дня") < text.index("💼 <b>Дела</b>")
        assert text.index("💼 <b>Дела</b>") < text.index("❤️ <b>Отношения</b>")
        assert text.index("❤️ <b>Отношения</b>") < text.index("⚡ <b>Энергия</b>")
        assert text.rstrip().endswith("Напиши тому, кто ждёт от тебя ответа.")

    def test_render_without_astro_context(self) -> None:
        text = prompt.render(_CARD, _TARGET, {}, _reading())
        assert "🌙" not in text
        assert "Колесница" in text

    def test_user_message_carries_card_and_transits(self) -> None:
        message = prompt.build_user_message(_CARD, _CONTEXT_V2, user_name="Аня", gender="женщина")
        assert "Колесница" in message
        assert "развилка_дня" in message
        assert "женщина" in message

    def test_user_message_without_chart_says_so(self) -> None:
        message = prompt.build_user_message(_CARD, {})
        assert "только по карте" in message


class TestCaption:
    def test_caption_is_card_plus_one_hook_phrase(self) -> None:
        caption = day_card_service.format_card_caption(_CARD)
        lines = caption.split("\n")
        assert len(lines) == 2
        assert "Колесница" in lines[0]
        assert lines[1].count(".") <= 1  # одна фраза, а не весь голос карты


def _user():
    user = MagicMock()
    user.id = uuid4()
    user.telegram_id = 1001
    user.profile = MagicMock(timezone="Europe/Moscow", display_name="Аня", gender="женщина")
    return user


class TestService:
    @pytest.mark.asyncio
    async def test_existing_card_is_not_redrawn(self) -> None:
        user = _user()
        draw = MagicMock(card_id="major_07", forecast=None)
        session = AsyncMock()
        with patch(
            "astra.services.day_card_service.tarot_crud.get_daily_draw",
            new=AsyncMock(return_value=draw),
        ):
            got_draw, card = await day_card_service.ensure_day_card(session, user, _TARGET)
        assert got_draw is draw
        assert card.id == "major_07"
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_card_excludes_previous_one(self) -> None:
        user = _user()
        session = AsyncMock()
        created = MagicMock(card_id="major_00", forecast=None)
        with (
            patch(
                "astra.services.day_card_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "astra.services.day_card_service.tarot_crud.get_previous_draw",
                new=AsyncMock(return_value=MagicMock(card_id="major_07")),
            ),
            patch(
                "astra.services.day_card_service.draw_card",
                return_value=card_by_id("major_00"),
            ) as draw_mock,
            patch(
                "astra.services.day_card_service.tarot_crud.create_draw",
                new=AsyncMock(return_value=created),
            ) as create_mock,
        ):
            await day_card_service.ensure_day_card(session, user, _TARGET)

        assert draw_mock.call_args.kwargs["exclude_ids"] == frozenset({"major_07"})
        assert create_mock.await_args.kwargs["context_kind"] == CONTEXT_DAY_CARD

    @pytest.mark.asyncio
    async def test_saved_forecast_returned_without_llm(self) -> None:
        user = _user()
        session = AsyncMock()
        draw = MagicMock(card_id="major_07", forecast="<b>готово</b>")
        with (
            patch(
                "astra.services.day_card_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=draw),
            ),
            patch(
                "astra.services.day_card_service._complete",
                new=AsyncMock(),
            ) as llm,
        ):
            outcome = await day_card_service.build_day_forecast(session, user, _TARGET)

        assert outcome.text == "<b>готово</b>"
        llm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_llm_reports_reason(self) -> None:
        user = _user()
        session = AsyncMock()
        draw = MagicMock(card_id="major_07", forecast=None)
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        with (
            patch(
                "astra.services.day_card_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=draw),
            ),
            patch(
                "astra.services.day_card_service.Redis.from_url",
                return_value=redis,
            ),
            patch(
                "astra.services.day_card_service._astro_context",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "astra.services.day_card_service._complete",
                new=AsyncMock(return_value=(None, "json_invalid")),
            ),
        ):
            outcome = await day_card_service.build_day_forecast(session, user, _TARGET)

        assert outcome.text is None
        assert outcome.failure_reason == "json_invalid"

    @pytest.mark.asyncio
    async def test_parallel_press_gets_in_progress(self) -> None:
        user = _user()
        session = AsyncMock()
        draw = MagicMock(card_id="major_07", forecast=None)
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)  # лок занят
        with (
            patch(
                "astra.services.day_card_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=draw),
            ),
            patch("astra.services.day_card_service.Redis.from_url", return_value=redis),
            patch("astra.services.day_card_service._complete", new=AsyncMock()) as llm,
        ):
            outcome = await day_card_service.build_day_forecast(session, user, _TARGET)

        assert outcome.failure_reason == "in_progress"
        llm.assert_not_awaited()


class TestMorningDelivery:
    @pytest.mark.asyncio
    async def test_day_card_sent_with_photo_and_button(self) -> None:
        user = _user()
        session = AsyncMock()
        task = TaskMessage(
            type=TaskType.DAY_CARD_SEND,
            user_id=user.id,
            prediction_date=_TARGET,
        )
        prediction = MagicMock(sent_at=None)
        with (
            patch(
                "astra.workers.handlers.users_crud.get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch(
                "astra.workers.handlers.predictions_crud.get_prediction_for_date",
                new=AsyncMock(return_value=prediction),
            ),
            patch("astra.workers.handlers.clear_progress", new=AsyncMock()),
            patch("astra.workers.handlers.clear_prediction_pending", new=AsyncMock()),
            patch("astra.workers.handlers.mark_prediction_sent", new=AsyncMock()) as mark,
            patch("astra.workers.handlers.deliver_day_card", new=AsyncMock()) as deliver,
        ):
            await handlers.handle_day_card_send(session, task)

        deliver.assert_awaited_once()
        mark.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_requeue_does_not_send_second_card(self) -> None:
        user = _user()
        session = AsyncMock()
        task = TaskMessage(
            type=TaskType.DAY_CARD_SEND,
            user_id=user.id,
            prediction_date=_TARGET,
        )
        with (
            patch(
                "astra.workers.handlers.users_crud.get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch(
                "astra.workers.handlers.predictions_crud.get_prediction_for_date",
                new=AsyncMock(return_value=MagicMock(sent_at="2026-07-22T06:00:00Z")),
            ),
            patch("astra.workers.handlers.clear_prediction_pending", new=AsyncMock()),
            patch("astra.workers.handlers.deliver_day_card", new=AsyncMock()) as deliver,
        ):
            await handlers.handle_day_card_send(session, task)

        deliver.assert_not_awaited()


class TestForecastButton:
    @pytest.mark.asyncio
    async def test_press_sends_forecast_and_removes_button(self) -> None:
        from astra.services.day_card_service import DayForecastOutcome
        from astra.telegram.handlers import day_card as handler

        callback = MagicMock()
        callback.from_user = MagicMock(id=1001)
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        callback.message.edit_reply_markup = AsyncMock()
        session = AsyncMock()

        with (
            patch(
                "astra.telegram.handlers.day_card.users_crud.get_user_by_telegram_id",
                new=AsyncMock(return_value=_user()),
            ),
            patch(
                "astra.telegram.handlers.day_card.build_day_forecast",
                new=AsyncMock(return_value=DayForecastOutcome(text="<b>прогноз</b>")),
            ),
        ):
            await handler.cb_day_card_forecast(callback, session)

        callback.message.edit_reply_markup.assert_awaited_once()
        assert callback.message.answer.await_args.args[0] == "<b>прогноз</b>"
        keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
        assert "Спросить карты" in keyboard.inline_keyboard[0][0].text

    @pytest.mark.asyncio
    async def test_second_parallel_press_stays_silent(self) -> None:
        from astra.services.day_card_service import DayForecastOutcome
        from astra.telegram.handlers import day_card as handler

        callback = MagicMock()
        callback.from_user = MagicMock(id=1001)
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        session = AsyncMock()

        with (
            patch(
                "astra.telegram.handlers.day_card.users_crud.get_user_by_telegram_id",
                new=AsyncMock(return_value=_user()),
            ),
            patch(
                "astra.telegram.handlers.day_card.build_day_forecast",
                new=AsyncMock(
                    return_value=DayForecastOutcome(text=None, failure_reason="in_progress"),
                ),
            ),
        ):
            await handler.cb_day_card_forecast(callback, session)

        callback.message.answer.assert_not_awaited()
