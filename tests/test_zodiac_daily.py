"""Тесты общего гороскопа по знакам и ветвления тарифа."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.astro.calculator import kerykeion_available
from astra.services.prediction_service import format_zodiac_daily_message


class TestZodiacPrompt:
    @pytest.mark.skipif(not kerykeion_available(), reason="kerykeion not installed")
    def test_user_message_has_real_transits(self):
        from astra.predictions.zodiac_daily import build_zodiac_user_message

        message, moon_note = build_zodiac_user_message("Близнецы", date(2026, 7, 7))
        assert "Близнецы" in message
        assert "аспекты_дня_к_знаку" in message
        assert moon_note is not None and moon_note.startswith("Луна в ")

    def test_sign_mid_lon_reference(self):
        from astra.predictions.zodiac_daily import _SIGN_MID_LON

        assert _SIGN_MID_LON["Овен"] == 15.0
        assert _SIGN_MID_LON["Близнецы"] == 75.0
        assert _SIGN_MID_LON["Рыбы"] == 345.0
        assert len(_SIGN_MID_LON) == 12


class TestZodiacCache:
    @pytest.mark.asyncio
    async def test_cached_row_skips_llm(self):
        from astra.predictions.zodiac_daily import get_or_generate_zodiac_daily

        cached = MagicMock()
        session = AsyncMock()
        with (
            patch(
                "astra.predictions.zodiac_daily.get_zodiac_daily",
                new=AsyncMock(return_value=cached),
            ),
            patch("astra.predictions.zodiac_daily._generate_zodiac_text") as gen,
        ):
            row = await get_or_generate_zodiac_daily(session, "Овен", date(2026, 7, 7))
        assert row is cached
        gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_rereads_cache(self):
        from astra.predictions.zodiac_daily import get_or_generate_zodiac_daily

        session = AsyncMock()
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)  # лок не взят
        late_row = MagicMock()
        with (
            patch(
                "astra.predictions.zodiac_daily.get_zodiac_daily",
                new=AsyncMock(side_effect=[None, late_row]),
            ),
            patch(
                "astra.predictions.zodiac_daily.Redis",
            ) as redis_cls,
            patch("astra.predictions.zodiac_daily._generate_zodiac_text") as gen,
        ):
            redis_cls.from_url.return_value = redis
            row = await get_or_generate_zodiac_daily(session, "Овен", date(2026, 7, 7))
        assert row is late_row
        gen.assert_not_called()


class TestTariffBranching:
    @pytest.mark.asyncio
    async def test_generic_flag_stores_zodiac_context(self):
        from astra.services.astro_service import build_and_store_daily_context

        user = MagicMock()
        user.id = MagicMock()
        profile = MagicMock()
        session = AsyncMock()
        chart = MagicMock()
        chart.sun_sign = "Близнецы"
        chart.accuracy_tier = 66
        cfg = MagicMock()
        cfg.personal_predictions_enabled = False

        stored = {}

        async def _upsert(sess, *, user_id, prediction_date, astro_context):
            stored.update(astro_context)
            return MagicMock()

        with (
            patch("astra.services.astro_service.get_settings", return_value=cfg),
            patch(
                "astra.services.astro_service.load_natal_chart_data",
                new=AsyncMock(return_value=chart),
            ),
            patch(
                "astra.services.astro_service.build_full_chart_for_user",
            ) as full_chart_mock,
            patch(
                "astra.services.astro_service.predictions_crud.upsert_context_draft",
                new=_upsert,
            ),
        ):
            await build_and_store_daily_context(session, user, profile, date(2026, 7, 7))

        assert stored["schema_version"] == "zodiac"
        assert stored["sign"] == "Близнецы"
        full_chart_mock.assert_not_called()  # полная карта не считается на общем тарифе


class TestZodiacMessageFormat:
    _TEXT = (
        "Что ты готов начать без гарантий?\n\n"
        "Марс в трине к твоему знаку даёт заряд для решительных шагов. "
        "Луна в Овне подгоняет — не затягивай с решениями.\n\n"
        "Сделай первый звонок до обеда."
    )

    def _prediction(self) -> SimpleNamespace:
        return SimpleNamespace(
            text=self._TEXT,
            astro_context={
                "schema_version": "zodiac",
                "date": "2026-07-07",
                "sign": "Близнецы",
                "moon_note": "Луна в Овне, последняя четверть",
            },
        )

    def test_zodiac_html_with_cta(self):
        html = format_zodiac_daily_message(self._prediction())
        assert html is not None
        assert html.startswith("🌙 <b>7 июля · Близнецы · Луна в Овне")
        assert "<i>Что ты готов начать без гарантий?</i>" in html
        assert "→ <b>Один шаг:</b> Сделай первый звонок до обеда." in html
        assert "Хочешь прогноз по своей карте" in html

    def test_v2_context_returns_none(self):
        prediction = SimpleNamespace(text=self._TEXT, astro_context={"schema_version": 2})
        assert format_zodiac_daily_message(prediction) is None
