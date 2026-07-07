"""Тесты Astrid v4: промпт, валидация без имени, сборка «Компаса», провайдер."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from astra.astro.daily_context import (
    DailyContextV2,
    DailyTransit,
    MoonContext,
    MoonSignChange,
    SphereOfDay,
)
from astra.llm.prompts.astrid import validate_prediction_output
from astra.llm.prompts.astrid_v4 import SYSTEM_PROMPT_V4, build_user_message_v4
from astra.services.prediction_service import format_compass_message


def _ctx(*, has_time: bool = True, archetype: str | None = "postpone") -> DailyContextV2:
    main = DailyTransit(
        transit_planet="Марс",
        transit_planet_key="Mars",
        aspect="трин",
        natal_point="Асцендент",
        natal_point_key="Ascendant",
        natal_sign="Весы",
        natal_house=1 if has_time else None,
        orb_deg=0.37,
        tightness=0.106,
    )
    return DailyContextV2(
        date=date(2026, 7, 7),
        accuracy_tier=100 if has_time else 33,
        has_time=has_time,
        big_three={"sun": "Близнецы", "moon": "Рыбы", "asc": "Весы" if has_time else None},
        main_transit=main,
        background=[],
        moon=MoonContext(
            sign="Овен",
            phase="последняя четверть",
            natal_house=7 if has_time else None,
            sign_change=MoonSignChange(to_sign="Телец", approx_hour=16),
        ),
        activated_natal_aspects=[],
        sphere_of_day=SphereOfDay(house=1, label="ты сам: самоподача и инициатива")
        if has_time
        else None,
        question_archetype_id=archetype,
    )


class TestPromptV4:
    def test_user_message_uses_prepositional_signs(self):
        message = build_user_message_v4(_ctx())
        assert "Асцендент в Весах" in message
        assert "в Весы" not in message

    def test_user_message_includes_moon_timing(self):
        message = build_user_message_v4(_ctx())
        assert "смена_знака" in message
        assert "16" in message

    def test_no_time_note_forbids_houses(self):
        message = build_user_message_v4(_ctx(has_time=False))
        assert "время рождения неизвестно" in message
        assert "натальный_дом" not in message

    def test_archetype_hint_included(self):
        message = build_user_message_v4(_ctx(archetype="postpone"))
        assert "Тип вопроса дня" in message
        no_hint = build_user_message_v4(_ctx(archetype=None))
        assert "Тип вопроса дня" not in no_hint

    def test_system_prompt_has_method_hierarchy(self):
        assert "main_transit" in SYSTEM_PROMPT_V4
        assert "activated_natal_aspects" in SYSTEM_PROMPT_V4
        assert "имя не используй" in SYSTEM_PROMPT_V4


class TestValidationWithoutName:
    _TEXT = (
        "Что ты откладываешь дольше, чем нужно?\n\n"
        "Марс в трине к твоему Асценденту даёт смелость действовать. "
        "Луна в Овне подогревает эмоции в разговорах с партнёром. "
        "Фоном Сатурн напоминает о границах.\n\n"
        "До обеда сделай первый шаг в отложенном деле."
    )

    def test_v4_mode_accepts_body_without_name(self):
        assert validate_prediction_output(self._TEXT, "Марина", require_name=False) is None

    def test_v3_mode_still_requires_name(self):
        assert validate_prediction_output(self._TEXT, "Марина") == "missing_name"


class TestCompassFormat:
    _BODY = (
        "Что скажешь, если не бояться ответа?\n\n"
        "Марс в трине к Асценденту — про смелость быть собой. "
        "Луна в Овне подогревает споры.\n\n"
        "Настоять на своём — или сберечь то, что между вами."
    )

    def _prediction(self, ctx: DailyContextV2 | None, text: str) -> SimpleNamespace:
        return SimpleNamespace(
            text=text,
            astro_context=ctx.model_dump(mode="json") if ctx else {"schema_version": 1},
        )

    def test_compass_html_assembled(self):
        from astra.services.prediction_service import TAROT_BRIDGE_TEXT

        html = format_compass_message(self._prediction(_ctx(), self._BODY))
        assert html is not None
        assert html.startswith("🌙 <b>7 июля · Луна в Овне, последняя четверть</b>")
        assert "<i>Что скажешь, если не бояться ответа?</i>" in html
        assert "⚖️ <b>Конфликт дня:</b> Настоять на своём — или сберечь" in html
        assert html.strip().endswith(TAROT_BRIDGE_TEXT)
        assert "Сфера дня" not in html  # сфера ушла из сообщения v4.1

    def test_v1_context_returns_none(self):
        assert format_compass_message(self._prediction(None, self._BODY)) is None

    def test_html_escaped(self):
        body = self._BODY.replace("про смелость", "про <смелость> & дерзость")
        html = format_compass_message(self._prediction(_ctx(), body))
        assert "&lt;смелость&gt; &amp; дерзость" in html


class TestProviderSelection:
    def test_deepseek_by_default(self):
        from astra.llm.daily_llm import get_daily_provider

        cfg = MagicMock()
        cfg.daily_llm_provider = "deepseek"
        with patch("astra.llm.daily_llm.get_deepseek_provider") as ds:
            get_daily_provider(cfg)
        ds.assert_called_once_with(cfg)

    def test_ollama_when_configured(self):
        from astra.llm.daily_llm import get_daily_provider

        cfg = MagicMock()
        cfg.daily_llm_provider = "ollama"
        with patch("astra.llm.daily_llm.get_ollama_provider") as ol:
            get_daily_provider(cfg)
        ol.assert_called_once_with(cfg)

    def test_enabled_flags(self):
        from astra.llm.daily_llm import daily_provider_enabled

        cfg = MagicMock()
        cfg.daily_llm_provider = "deepseek"
        cfg.deepseek_enabled = True
        cfg.deepseek_api_key = "sk-x"
        assert daily_provider_enabled(cfg)
        cfg.deepseek_api_key = ""
        assert not daily_provider_enabled(cfg)
        cfg.daily_llm_provider = "ollama"
        cfg.ollama_enabled = True
        assert daily_provider_enabled(cfg)
