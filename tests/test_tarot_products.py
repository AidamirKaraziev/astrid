"""Тесты продуктов таро: у каждого своя схема, промпт, валидация и формат.

Проверяем главное свойство JSON-подхода: позиция↔текст детерминированы,
съехать (как при парсинге абзацев) физически невозможно.
"""

import pytest

from astra.llm.prompts.tarot_spreads import TAROT_PRODUCTS
from astra.llm.prompts.tarot_spreads.relationship import RelationshipReading
from astra.llm.prompts.tarot_spreads.three_cards import ThreeCardsReading
from astra.llm.prompts.tarot_spreads.yes_no import YesNoReading
from astra.tarot.deck import card_by_id
from astra.tarot.spreads import SpreadType

_LONG = "Достаточно длинный осмысленный текст блока про эту позицию расклада сегодня."


class TestRegistry:
    def test_every_spread_has_a_product(self):
        assert set(TAROT_PRODUCTS) == set(SpreadType)

    def test_each_product_has_distinct_prompt_and_schema(self):
        prompts = {p.system_prompt for p in TAROT_PRODUCTS.values()}
        schemas = {p.schema for p in TAROT_PRODUCTS.values()}
        assert len(prompts) == 3
        assert schemas == {YesNoReading, ThreeCardsReading, RelationshipReading}

    def test_prompts_use_cyrillic_persona_and_forbid_greetings(self):
        for product in TAROT_PRODUCTS.values():
            assert "Астрид" in product.system_prompt
            assert "НЕ обращайся" in product.system_prompt  # запрет вступлений/имени
            assert "JSON" in product.system_prompt


class TestBuildUserMessage:
    def test_includes_question_positions_and_client(self):
        product = TAROT_PRODUCTS[SpreadType.THREE_CARDS]
        cards = [card_by_id("wands_01"), card_by_id("wands_10"), card_by_id("cups_06")]
        msg = product.build_user_message(
            "работать ли с Анжелой?", cards, user_name="Аня", gender="женщина",
        )
        assert "работать ли с Анжелой?" in msg
        assert "Туз Жезлов" in msg and "heart" in msg  # поле позиции
        assert "женщина" in msg and "Аня" in msg

    def test_client_omitted_without_profile(self):
        product = TAROT_PRODUCTS[SpreadType.YES_NO]
        msg = product.build_user_message("вопрос?", [card_by_id("major_07")])
        assert "клиент" not in msg


class TestParse:
    def test_valid_json_parses(self):
        product = TAROT_PRODUCTS[SpreadType.THREE_CARDS]
        raw = '{"heart":"a","hidden":"b","outcome":"c","summary":"d"}'
        assert isinstance(product.parse(raw), ThreeCardsReading)

    def test_code_fence_stripped(self):
        product = TAROT_PRODUCTS[SpreadType.YES_NO]
        raw = '```json\n{"verdict":"да","answer":"a","summary":"b"}\n```'
        assert product.parse(raw) is not None

    def test_invalid_json_returns_none(self):
        product = TAROT_PRODUCTS[SpreadType.YES_NO]
        assert product.parse("это не json, а просто текст") is None

    def test_missing_field_returns_none(self):
        product = TAROT_PRODUCTS[SpreadType.THREE_CARDS]
        assert product.parse('{"heart":"a","hidden":"b"}') is None


class TestYesNo:
    product = TAROT_PRODUCTS[SpreadType.YES_NO]

    def test_verdict_required(self):
        data = YesNoReading(verdict="возможно", answer=_LONG, summary="итог достаточной длины тут")
        assert self.product.validate(data) == "missing_verdict"

    def test_valid(self):
        data = YesNoReading(verdict="да, но", answer=_LONG, summary="итог достаточной длины тут")
        assert self.product.validate(data) is None

    def test_render_shows_verdict_in_summary(self):
        data = YesNoReading(verdict="да, но", answer=_LONG, summary="сделай один конкретный шаг сегодня")
        out = self.product.render("стоит ли?", [card_by_id("wands_queen")], data)
        assert "Расклад на решение" in out
        assert "Итог — Да, но:" in out
        assert "Королева Жезлов" in out


class TestThreeCardsAlignment:
    product = TAROT_PRODUCTS[SpreadType.THREE_CARDS]

    def test_each_position_gets_its_own_field(self):
        cards = [card_by_id("wands_01"), card_by_id("wands_10"), card_by_id("cups_06")]
        data = ThreeCardsReading(
            heart="СЕРДЦЕ-текст достаточной длины про суть вопроса на поверхности.",
            hidden="СКРЫТОЕ-текст достаточной длины про неочевидный фактор внутри.",
            outcome="ИСХОД-текст достаточной длины про то, к чему всё идёт дальше.",
            summary="итог достаточной длины с конкретным действием на сегодня",
        )
        assert self.product.validate(data) is None
        out = self.product.render("вопрос?", cards, data)
        # текст позиции стоит ровно под своей картой — без сдвига
        assert "Сердце вопроса — Туз Жезлов</b>\nСЕРДЦЕ-текст" in out
        assert "Скрытое течение — Десятка Жезлов</b>\nСКРЫТОЕ-текст" in out
        assert "К чему идёт — Шестёрка Кубков</b>\nИСХОД-текст" in out

    def test_position_emoji_used_not_card_emoji(self):
        cards = [card_by_id("wands_01"), card_by_id("wands_10"), card_by_id("cups_06")]
        data = ThreeCardsReading(heart=_LONG, hidden=_LONG, outcome=_LONG, summary=_LONG)
        out = self.product.render("вопрос?", cards, data)
        assert "💛 <b>Сердце вопроса" in out
        assert "🌊 <b>Скрытое течение" in out
        assert "🔮 <b>К чему идёт" in out

    def test_short_field_rejected(self):
        data = ThreeCardsReading(heart="мало", hidden=_LONG, outcome=_LONG, summary=_LONG)
        assert self.product.validate(data) == "field_heart_too_short"


class TestRelationship:
    product = TAROT_PRODUCTS[SpreadType.RELATIONSHIP]

    def test_valid_and_five_blocks_rendered(self):
        cards = [
            card_by_id(c)
            for c in ("major_06", "cups_queen", "swords_03", "pentacles_04", "wands_10")
        ]
        data = RelationshipReading(
            you=_LONG, partner=_LONG, between=_LONG, obstacle=_LONG, direction=_LONG,
            summary="итог достаточной длины с конкретным действием на неделю",
        )
        assert self.product.validate(data) is None
        out = self.product.render("что между нами?", cards, data)
        for label in ("Ты —", "Он(а) —", "Между вами —", "Что мешает —", "Куда это идёт —"):
            assert label in out
        assert "html" not in out  # эскейпа мусора нет

    def test_question_html_escaped(self):
        cards = [card_by_id(c) for c in ("major_06", "cups_queen", "swords_03", "pentacles_04", "wands_10")]
        data = RelationshipReading(
            you=_LONG, partner=_LONG, between=_LONG, obstacle=_LONG, direction=_LONG,
            summary="итог достаточной длины с конкретным действием на неделю",
        )
        out = self.product.render("<b>взлом</b>", cards, data)
        assert "<b>взлом</b>" not in out
        assert "&lt;b&gt;" in out
