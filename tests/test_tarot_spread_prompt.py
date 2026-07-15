"""Тесты спек раскладов и промпта: структура, нормализация, валидация."""

from astra.llm.prompts.tarot_spread import (
    build_spread_user_message,
    normalize_spread_blocks,
    validate_spread_output,
)
from astra.tarot.deck import card_by_id
from astra.tarot.spreads import SPREADS, SpreadType

_YES_NO = SPREADS[SpreadType.YES_NO]
_THREE = SPREADS[SpreadType.THREE_CARDS]
_REL = SPREADS[SpreadType.RELATIONSHIP]

_BLOCK = "Карта в этой позиции говорит о движении и выборе стороны без спешки сегодня."
_SUMMARY_YES = "Да, но сначала закрой начатое — карта просит одного конкретного шага."
_SUMMARY = "Итог складывается в пользу разговора — начни его сегодня сама."


class TestSpecs:
    def test_spread_shapes(self):
        assert _YES_NO.card_count == 1 and _YES_NO.question_required
        assert _THREE.card_count == 3 and not _THREE.question_required
        assert _REL.card_count == 5 and _REL.question_required

    def test_position_keys_unique(self):
        for spec in SPREADS.values():
            keys = [p.key for p in spec.positions]
            assert len(keys) == len(set(keys)), spec.type


class TestBuildMessage:
    def test_contains_cards_positions_and_question(self):
        cards = [card_by_id("major_07"), card_by_id("cups_02"), card_by_id("wands_10")]
        message = build_spread_user_message(_THREE, "Что с моей работой?", cards)
        assert "Что с моей работой?" in message
        assert "Колесница" in message and "Двойка Кубков" in message
        assert "Прошлое" in message and "Будущее" in message
        assert '"число_блоков_в_ответе": 4' in message

    def test_no_question_fallback(self):
        message = build_spread_user_message(_THREE, None, [card_by_id("major_00")] * 3)
        assert "вопрос не задан" in message


class TestNormalize:
    def test_extra_blocks_merged_into_summary(self):
        text = "\n\n".join([_BLOCK, _BLOCK, _BLOCK, _SUMMARY, "И ещё хвост."])
        normalized = normalize_spread_blocks(_THREE, text)
        blocks = normalized.split("\n\n")
        assert len(blocks) == 4
        assert blocks[-1].endswith("И ещё хвост.")

    def test_expected_count_untouched(self):
        text = "\n\n".join([_BLOCK, _SUMMARY_YES])
        assert normalize_spread_blocks(_YES_NO, text) == text


class TestValidate:
    def test_valid_yes_no(self):
        assert validate_spread_output(_YES_NO, f"{_BLOCK}\n\n{_SUMMARY_YES}") is None

    def test_yes_no_without_verdict(self):
        text = f"{_BLOCK}\n\n{_SUMMARY}"
        assert validate_spread_output(_YES_NO, text) == "missing_verdict"

    def test_verdict_with_quotes_accepted(self):
        text = f"{_BLOCK}\n\n«Да, но не раньше пятницы — карта просит паузы и тишины.»"
        assert validate_spread_output(_YES_NO, text) is None

    def test_wrong_block_count(self):
        assert validate_spread_output(_THREE, f"{_BLOCK}\n\n{_SUMMARY}") == "invalid_structure"

    def test_short_position_block(self):
        text = "\n\n".join(["Коротко.", _BLOCK, _BLOCK, _SUMMARY])
        assert validate_spread_output(_THREE, text) == "position_block_too_short"

    def test_short_summary(self):
        text = "\n\n".join([_BLOCK, _BLOCK, _BLOCK, "Всё."])
        assert validate_spread_output(_THREE, text) == "summary_too_short"

    def test_valid_relationship(self):
        text = "\n\n".join([_BLOCK] * 5 + [_SUMMARY])
        assert validate_spread_output(_REL, text) is None
