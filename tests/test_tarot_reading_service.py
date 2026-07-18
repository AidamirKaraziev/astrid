"""Тесты сервиса раскладов: генерация JSON с retry, идемпотентная доставка."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from astra.llm.types import CompletionResult
from astra.services.tarot_reading_service import (
    check_daily_limit,
    create_reading,
    deliver_reading,
    format_reading_caption,
    generate_reading_interpretation,
)
from astra.tarot.deck import card_by_id
from astra.tarot.enums import ReadingStatus
from astra.tarot.spreads import SPREADS, SpreadType

_MODULE = "astra.services.tarot_reading_service"

_YES_NO_JSON = (
    '{"verdict":"да, но",'
    '"answer":"Королева Жезлов отвечает: да, если понесёшь дело как свой огонь, а не побег.",'
    '"summary":"Начинай — запиши три услуги и покажи одному реальному клиенту на этой неделе."}'
)


def _reading_mock(spread_type: str = SpreadType.YES_NO, **overrides) -> MagicMock:
    reading = MagicMock()
    reading.id = uuid4()
    reading.user_id = uuid4()
    reading.spread_type = spread_type
    reading.question = "Стоит ли менять работу?"
    reading.cards = [
        {"position": 1, "position_key": "answer", "card_id": "major_07", "reversed": False},
    ]
    reading.interpretation = None
    reading.status = ReadingStatus.PENDING
    reading.sent_at = None
    for key, value in overrides.items():
        setattr(reading, key, value)
    return reading


def _provider_mock(*results: CompletionResult) -> MagicMock:
    provider = MagicMock()
    provider.name = "deepseek"
    provider.complete = AsyncMock(side_effect=list(results))
    return provider


def _patch_user(name: str = "Аня", gender: str = "женщина"):
    user = MagicMock()
    user.profile = MagicMock(display_name=name, gender=gender)
    return patch(f"{_MODULE}.users_crud.get_user_by_id", AsyncMock(return_value=user))


class TestCheckDailyLimit:
    async def test_under_limit(self):
        session, user = AsyncMock(), MagicMock()
        with (
            patch(f"{_MODULE}.tarot_crud.count_readings_for_date", AsyncMock(return_value=0)),
            patch(f"{_MODULE}.granted_bonus", AsyncMock(return_value=0)),
        ):
            assert await check_daily_limit(session, user, date(2026, 7, 15)) is True

    async def test_limit_reached(self):
        session, user = AsyncMock(), MagicMock()
        with (
            patch(f"{_MODULE}.tarot_crud.count_readings_for_date", AsyncMock(return_value=1)),
            patch(f"{_MODULE}.granted_bonus", AsyncMock(return_value=0)),
        ):
            assert await check_daily_limit(session, user, date(2026, 7, 15)) is False

    async def test_bonus_raises_limit(self):
        session, user = AsyncMock(), MagicMock()
        with (
            patch(f"{_MODULE}.tarot_crud.count_readings_for_date", AsyncMock(return_value=1)),
            patch(f"{_MODULE}.granted_bonus", AsyncMock(return_value=1)),
        ):
            assert await check_daily_limit(session, user, date(2026, 7, 15)) is True


class TestCreateReading:
    async def test_cards_json_matches_spec_positions(self):
        session, user = AsyncMock(), MagicMock(id=uuid4())
        created = {}

        async def capture(session_, **kwargs):
            created.update(kwargs)
            return MagicMock(id=uuid4())

        with patch(f"{_MODULE}.tarot_crud.create_reading", AsyncMock(side_effect=capture)):
            _, cards = await create_reading(
                session, user, SpreadType.RELATIONSHIP, "Что между нами?", date(2026, 7, 15),
            )
        assert len(cards) == 5
        keys = [entry["position_key"] for entry in created["cards"]]
        assert keys == ["you", "partner", "between", "obstacle", "direction"]
        card_ids = [entry["card_id"] for entry in created["cards"]]
        assert len(card_ids) == len(set(card_ids))
        assert all(entry["reversed"] is False for entry in created["cards"])


class TestGenerateInterpretation:
    async def test_success_renders_and_marks_text_ready(self):
        session = AsyncMock()
        reading = _reading_mock()
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            _patch_user(),
            patch(
                f"{_MODULE}.get_daily_provider",
                return_value=_provider_mock(CompletionResult(_YES_NO_JSON, None)),
            ),
        ):
            result = await generate_reading_interpretation(session, reading.id)
        assert result is reading
        assert reading.status == ReadingStatus.TEXT_READY
        # interpretation — уже готовое отрендеренное сообщение
        assert "Итог — Да, но:" in reading.interpretation
        assert "Расклад на решение" in reading.interpretation

    async def test_json_mode_and_profile_passed_to_llm(self):
        session = AsyncMock()
        reading = _reading_mock()
        provider = _provider_mock(CompletionResult(_YES_NO_JSON, None))
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            _patch_user(name="Марк", gender="мужчина"),
            patch(f"{_MODULE}.get_daily_provider", return_value=provider),
        ):
            await generate_reading_interpretation(session, reading.id)
        request = provider.complete.await_args.args[0]
        assert request.extra.get("json_mode") is True
        user_message = request.messages[1].content
        assert "Марк" in user_message and "мужчина" in user_message

    async def test_invalid_json_then_success(self):
        session = AsyncMock()
        reading = _reading_mock()
        provider = _provider_mock(
            CompletionResult("это не json", None),
            CompletionResult(_YES_NO_JSON, None),
        )
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            _patch_user(),
            patch(f"{_MODULE}.get_daily_provider", return_value=provider),
        ):
            result = await generate_reading_interpretation(session, reading.id)
        assert result is reading
        assert provider.complete.await_count == 2

    async def test_abandon_marks_failed(self):
        session = AsyncMock()
        reading = _reading_mock()
        provider = _provider_mock(
            CompletionResult("не json", None),
            CompletionResult(None, "http_500"),
        )
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            _patch_user(),
            patch(f"{_MODULE}.get_daily_provider", return_value=provider),
        ):
            result = await generate_reading_interpretation(session, reading.id)
        assert result is None
        assert reading.status == ReadingStatus.FAILED
        assert reading.failure_reason == "http_500"

    async def test_verdict_missing_is_validation_failure(self):
        session = AsyncMock()
        reading = _reading_mock()
        bad = '{"verdict":"возможно","answer":"' + "x" * 50 + '","summary":"' + "y" * 30 + '"}'
        provider = _provider_mock(
            CompletionResult(bad, None),
            CompletionResult(bad, None),
        )
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            _patch_user(),
            patch(f"{_MODULE}.get_daily_provider", return_value=provider),
        ):
            result = await generate_reading_interpretation(session, reading.id)
        assert result is None
        assert reading.failure_reason == "missing_verdict"

    async def test_idempotent_when_text_ready(self):
        session = AsyncMock()
        reading = _reading_mock(interpretation="готовое", status=ReadingStatus.TEXT_READY)
        provider = _provider_mock()
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.get_daily_provider", return_value=provider),
        ):
            result = await generate_reading_interpretation(session, reading.id)
        assert result is reading
        provider.complete.assert_not_awaited()


class TestDeliverReading:
    async def test_sends_stored_interpretation_and_marks(self):
        session = AsyncMock()
        reading = _reading_mock(
            interpretation="🃏 <b>Три карты</b>\n\n...готовое сообщение...",
            status=ReadingStatus.TEXT_READY,
        )
        user = MagicMock(telegram_id=42)
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.users_crud.get_user_by_id", AsyncMock(return_value=user)),
            patch(f"{_MODULE}.send_telegram_html", AsyncMock()) as send,
            patch(f"{_MODULE}.tarot_crud.mark_reading_sent", AsyncMock()) as mark,
        ):
            assert await deliver_reading(session, reading.id) is True
        send.assert_awaited_once()
        assert send.await_args.args[0] == 42
        assert send.await_args.args[1] == reading.interpretation
        mark.assert_awaited_once()

    async def test_idempotent_when_already_sent(self):
        session = AsyncMock()
        reading = _reading_mock(interpretation="готовое", sent_at=MagicMock())
        with (
            patch(f"{_MODULE}.tarot_crud.get_reading", AsyncMock(return_value=reading)),
            patch(f"{_MODULE}.send_telegram_html", AsyncMock()) as send,
        ):
            assert await deliver_reading(session, reading.id) is False
        send.assert_not_awaited()


class TestCaption:
    def test_caption_lists_positions_and_cards(self):
        spec = SPREADS[SpreadType.YES_NO]
        caption = format_reading_caption(spec, [card_by_id("major_07")])
        assert "Расклад на решение" in caption
        assert "Ответ:" in caption and "Колесница" in caption
        assert len(caption) <= 1024

    def test_relationship_caption_fits_album_limit(self):
        spec = SPREADS[SpreadType.RELATIONSHIP]
        cards = [
            card_by_id(card_id)
            for card_id in ("major_06", "cups_queen", "swords_03", "pentacles_04", "wands_10")
        ]
        caption = format_reading_caption(spec, cards)
        assert len(caption) <= 1024
        assert "Между вами:" in caption and "Королева Кубков" in caption
