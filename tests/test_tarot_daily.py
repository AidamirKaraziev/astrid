"""Тесты раскрытия карты дня: лимит, идемпотентность, промпт, формат."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.llm.prompts.tarot_daily import build_tarot_user_message, validate_tarot_output
from astra.services.tarot_daily_service import format_tarot_reveal, reveal_daily_card
from astra.tarot.deck import card_by_id

_CHARIOT = card_by_id("major_07")

_V2_CONTEXT = {
    "schema_version": 2,
    "has_time": True,
    "conflict": {
        "side_a": "Марс трин Асцендент (орб 0.37°, гармония)",
        "side_b": "Луна соединение Марс (орб 1.16°, обострение)",
    },
    "main_transit": {
        "transit_planet": "Марс",
        "aspect": "трин",
        "natal_point": "Асцендент",
        "orb_deg": 0.37,
    },
    "moon": {"sign": "Овен", "phase": "последняя четверть"},
    "activated_natal_aspects": [{"p1": "Меркурий", "aspect": "трин", "p2": "Асцендент"}],
}

_INTERPRETATION = (
    "Колесница не выбрала ни одну из сторон — она про то, чтобы держать обе "
    "лошади в одних руках: твой Марс даёт силу, а Луна проверяет мягкость.\n\n"
    "До 16:00 скажи главное спокойно один раз."
)


class TestPrompt:
    def test_user_message_with_conflict(self):
        message = build_tarot_user_message(_CHARIOT, _V2_CONTEXT)
        assert "Колесница" in message
        assert "conflict" in message
        assert "Марс трин Асцендент" in message
        assert "Рак" in message  # астро-соответствие карты

    def test_zodiac_context(self):
        ctx = {"schema_version": "zodiac", "sign": "Близнецы", "moon_note": "Луна в Овне"}
        message = build_tarot_user_message(_CHARIOT, ctx)
        assert "Близнецы" in message
        assert "натальной карты нет" in message

    def test_empty_context_fallback(self):
        message = build_tarot_user_message(_CHARIOT, {})
        assert "прогноза на сегодня нет" in message

    def test_validate_output(self):
        assert validate_tarot_output(_INTERPRETATION) is None
        assert validate_tarot_output("Коротко.") == "invalid_structure"
        assert validate_tarot_output("Мало.\n\nШаг тут нормальной длины.") == (
            "interpretation_too_short"
        )


class TestReveal:
    def _user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_repeat_returns_existing_without_llm(self):
        existing = MagicMock()
        existing.card_id = "major_07"
        session = AsyncMock()
        with (
            patch(
                "astra.services.tarot_daily_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=existing),
            ),
            patch(
                "astra.services.tarot_daily_service._generate_interpretation",
            ) as gen,
        ):
            outcome = await reveal_daily_card(session, self._user(), date(2026, 7, 7))
        assert outcome.already_drawn
        assert outcome.card is _CHARIOT
        gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_draw_saves_conflict_and_interpretation(self):
        session = AsyncMock()
        prediction = MagicMock()
        prediction.astro_context = _V2_CONTEXT
        saved = {}

        async def _create(sess, **kwargs):
            saved.update(kwargs)
            row = MagicMock()
            row.card_id = kwargs["card_id"]
            row.interpretation = kwargs["interpretation"]
            return row

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        with (
            patch(
                "astra.services.tarot_daily_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "astra.services.tarot_daily_service.tarot_crud.get_previous_draw",
                new=AsyncMock(return_value=None),
            ),
            patch("astra.services.tarot_daily_service.Redis") as redis_cls,
            patch(
                "astra.services.tarot_daily_service.predictions_crud.get_prediction_for_date",
                new=AsyncMock(return_value=prediction),
            ),
            patch(
                "astra.services.tarot_daily_service._generate_interpretation",
                new=AsyncMock(return_value=(_INTERPRETATION, "")),
            ),
            patch(
                "astra.services.tarot_daily_service.tarot_crud.create_draw",
                new=_create,
            ),
        ):
            redis_cls.from_url.return_value = redis
            outcome = await reveal_daily_card(session, self._user(), date(2026, 7, 7))

        assert outcome.draw is not None and not outcome.already_drawn
        assert saved["conflict_text"] is not None and "vs" in saved["conflict_text"]
        assert saved["interpretation"] == _INTERPRETATION

    @pytest.mark.asyncio
    async def test_llm_failure_does_not_save_draw(self):
        session = AsyncMock()
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        with (
            patch(
                "astra.services.tarot_daily_service.tarot_crud.get_daily_draw",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "astra.services.tarot_daily_service.tarot_crud.get_previous_draw",
                new=AsyncMock(return_value=None),
            ),
            patch("astra.services.tarot_daily_service.Redis") as redis_cls,
            patch(
                "astra.services.tarot_daily_service.predictions_crud.get_prediction_for_date",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "astra.services.tarot_daily_service._generate_interpretation",
                new=AsyncMock(return_value=(None, "empty_response")),
            ),
            patch(
                "astra.services.tarot_daily_service.tarot_crud.create_draw",
            ) as create_mock,
        ):
            redis_cls.from_url.return_value = redis
            outcome = await reveal_daily_card(session, self._user(), date(2026, 7, 7))

        assert outcome.draw is None
        assert outcome.failure_reason == "empty_response"
        create_mock.assert_not_called()


class TestRevealFormat:
    def test_first_reveal(self):
        html = format_tarot_reveal(_CHARIOT, _INTERPRETATION)
        assert html.startswith("🎴 <b>Я спросила карты о твоей развилке.</b>")
        assert "<b>Колесница</b> 🏇" in html
        assert html.endswith("→ <b>Один шаг:</b> До 16:00 скажи главное спокойно один раз.")

    def test_repeated_reveal(self):
        html = format_tarot_reveal(_CHARIOT, _INTERPRETATION, repeated=True)
        assert "Колода уже ответила тебе сегодня" in html
        assert "путает нити" in html


class TestNormalize:
    def test_single_paragraph_splits_last_sentence_as_step(self):
        from astra.llm.prompts.tarot_daily import normalize_tarot_blocks

        merged = (
            "Звезда не выбирает стороны, потому что обе гармоничны. "
            "Марс даёт телу энергию, а Луна требует завершения. "
            "Сейчас важнее ясность, чем победа. "
            "До 23:00 запиши одну фразу о своих чувствах."
        )
        normalized = normalize_tarot_blocks(merged)
        blocks = normalized.split("\n\n")
        assert len(blocks) == 2
        assert blocks[1].startswith("До 23:00")
        assert validate_tarot_output(normalized) is None

    def test_two_blocks_untouched(self):
        from astra.llm.prompts.tarot_daily import normalize_tarot_blocks

        assert normalize_tarot_blocks(_INTERPRETATION) == _INTERPRETATION
