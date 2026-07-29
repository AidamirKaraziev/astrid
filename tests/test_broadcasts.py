"""Рассылки: отбор аудитории, ИИ-редактор и проверка разметки."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from astra.broadcasts.audience import (
    ZODIAC_NAMES,
    Criteria,
    build_query,
    zodiac_bounds,
)
from astra.broadcasts.editor import ALLOWED_TAGS, check, improve, personalize_text
from astra.llm.prompts.broadcast import (
    FORBIDDEN_EMOJI,
    MAX_LENGTH,
    SYSTEM_PROMPT,
    build_user_message,
)

_EDITOR = "astra.broadcasts.editor"


class TestZodiac:
    def test_all_twelve_signs(self):
        assert len(ZODIAC_NAMES) == 12
        assert "Овен" in ZODIAC_NAMES and "Рыбы" in ZODIAC_NAMES

    def test_bounds_of_a_normal_sign(self):
        assert zodiac_bounds("Овен") == ((3, 21), (4, 19))

    def test_capricorn_crosses_new_year(self):
        """Козерог начинается в декабре и заканчивается в январе — особый случай."""
        start, end = zodiac_bounds("Козерог")
        assert start == (12, 22)
        assert end == (1, 19)

    def test_unknown_sign(self):
        assert zodiac_bounds("Змееносец") is None


class TestCriteria:
    def test_empty_by_default(self):
        assert Criteria().is_empty()

    def test_any_filter_makes_it_non_empty(self):
        assert not Criteria(zodiac={"Овен"}).is_empty()
        assert not Criteria(money="never").is_empty()

    def test_blocked_users_always_excluded(self):
        """Слать заблокировавшим бессмысленно, а охват они завышают."""
        sql = str(build_query(Criteria()))
        assert "bot_blocked_at IS NULL" in sql

    def test_conditions_are_combined_with_and(self):
        sql = str(build_query(Criteria(zodiac={"Овен"}, money="paid", onboarding="done")))
        assert sql.count("users.id IN") >= 2

    def test_exclusions_subtract(self):
        sql = str(build_query(Criteria(money="paid", exclude_active_within_days=7)))
        assert "NOT IN" in sql

    def test_sleeping_is_absence_of_activity(self):
        sql = str(build_query(Criteria(sleeping_since_days=14)))
        assert "NOT IN" in sql
        assert "activity_days" in sql


class TestMarkupCheck:
    def test_clean_message_passes(self):
        assert check("<b>Колесо</b> ждёт тебя 💫\n\nЗагляни вечером.") == ()

    def test_unknown_tag_caught(self):
        problems = check("<div>Привет</div>")
        assert any("не поймёт теги" in problem for problem in problems)

    def test_unclosed_tag_caught(self):
        problems = check("<b>Привет")
        assert any("<b>" in problem for problem in problems)

    def test_markdown_caught(self):
        """Модель любит скатываться в markdown — Telegram покажет звёздочки."""
        problems = check("**жирный**")
        assert any("markdown" in problem for problem in problems)

    def test_interface_emoji_rejected(self):
        problems = check("Готово ✅")
        assert any("служебные значки" in problem for problem in problems)

    def test_palette_emoji_allowed(self):
        assert check("Твоя карта дня 🔮 уже ждёт ✨") == ()

    def test_empty_message_caught(self):
        assert any("пустое" in problem for problem in check("   "))

    def test_all_telegram_tags_known(self):
        for tag in ("b", "i", "u", "s", "a", "code", "blockquote", "tg-spoiler"):
            assert tag in ALLOWED_TAGS


class TestPersonalize:
    def test_name_prefixed_and_sentence_lowered(self):
        assert personalize_text("Твоё колесо ждёт\nЗагляни", "Алина").startswith(
            "Алина, твоё колесо ждёт",
        )

    def test_without_name_text_untouched(self):
        text = "Твоё колесо ждёт"
        assert personalize_text(text, None) == text
        assert personalize_text(text, "  ") == text


class TestPrompt:
    def test_written_in_english_but_asks_for_russian(self):
        """Конвенция проекта: промпт английский, ответ модели — русский."""
        assert "WRITE IN RUSSIAN" in SYSTEM_PROMPT
        assert "Astrid" in SYSTEM_PROMPT

    def test_forbids_interface_emoji(self):
        for emoji in ("🔁", "⚙️", "➡️"):
            assert emoji in FORBIDDEN_EMOJI
        assert FORBIDDEN_EMOJI in SYSTEM_PROMPT

    def test_limits_length_and_markup(self):
        assert str(MAX_LENGTH) in SYSTEM_PROMPT
        assert "<tg-spoiler>" in SYSTEM_PROMPT
        assert "Never use markdown" in SYSTEM_PROMPT

    def test_facts_are_protected(self):
        assert "Changing any number" in SYSTEM_PROMPT
        assert "Inventing prices" in SYSTEM_PROMPT

    def test_user_message_carries_context(self):
        message = build_user_message("Привет", audience_note="спящие 14 дней", personalize=True)
        assert "Привет" in message
        assert "спящие 14 дней" in message
        assert "name" in message.lower()

    def test_personalisation_note_absent_when_off(self):
        assert "Personalisation" not in build_user_message("Привет")


class TestImprove:
    async def _improve(self, answer: str | None, reason: str = ""):
        result = SimpleNamespace(text=answer, reason=reason)
        provider = SimpleNamespace(complete=AsyncMock(return_value=result))
        with patch(f"{_EDITOR}.get_llm_provider", return_value=provider):
            return await improve("Колесо ждёт")

    async def test_returns_model_text(self):
        draft = await self._improve("<b>Колесо ждёт</b> 💫")
        assert draft.text == "<b>Колесо ждёт</b> 💫"
        assert draft.warnings == ()

    async def test_code_fence_stripped(self):
        """Модель оборачивает ответ в ```html — до людей это доходить не должно."""
        draft = await self._improve("```html\n<b>Колесо</b>\n```")
        assert draft.text == "<b>Колесо</b>"

    async def test_quotes_stripped(self):
        draft = await self._improve('"Колесо ждёт"')
        assert draft.text == "Колесо ждёт"

    async def test_model_silence_keeps_authors_text(self):
        draft = await self._improve(None, reason="timeout")
        assert draft.text == "Колесо ждёт"
        assert any("модель не ответила" in warning for warning in draft.warnings)

    async def test_bad_markup_from_model_is_flagged(self):
        draft = await self._improve("<div>Колесо</div> ✅")
        assert draft.warnings
        assert any("не поймёт теги" in warning for warning in draft.warnings)
