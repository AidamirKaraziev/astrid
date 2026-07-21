"""Подсказка при вводе вопроса должна считываться одним взглядом.

Экран расклада — единственное место, где пользователь должен что-то напечатать
сам, поэтому действие вынесено в первую строку, а пример идёт отдельным блоком.
Разметка отправляется с parse_mode=HTML: незакрытый тег — отказ Telegram
отправить сообщение целиком, то есть экран вопроса просто не появится.
"""

from html.parser import HTMLParser

import pytest

from astra.tarot.spreads import SPREADS, SpreadType

_ALLOWED_TAGS = {"b", "i"}


class _TagBalance(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.unknown: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in _ALLOWED_TAGS:
            self.unknown.append(tag)
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.stack.append(f"!{tag}")


@pytest.mark.parametrize("spread_type", list(SpreadType))
class TestQuestionHint:
    def test_html_is_balanced_and_allowed(self, spread_type: SpreadType) -> None:
        parser = _TagBalance()
        parser.feed(SPREADS[spread_type].question_hint)
        assert parser.stack == [], f"незакрытые теги: {parser.stack}"
        assert parser.unknown == [], f"Telegram не поймёт теги: {parser.unknown}"

    def test_first_line_is_the_action(self, spread_type: SpreadType) -> None:
        first = SPREADS[spread_type].question_hint.splitlines()[0]
        assert first.startswith("✍️"), first
        assert "<b>" in first and "</b>" in first, first
        assert "Напиши" in first, first

    def test_shows_example(self, spread_type: SpreadType) -> None:
        hint = SPREADS[spread_type].question_hint
        assert "Например:" in hint
        assert "<i>«" in hint  # пример выделен и закавычен

    def test_stays_scannable(self, spread_type: SpreadType) -> None:
        hint = SPREADS[spread_type].question_hint
        lines = [line for line in hint.splitlines() if line.strip()]
        assert len(lines) <= 6, f"слишком много строк: {len(lines)}"
        longest = max(len(line) for line in lines)
        assert longest <= 70, f"строка не влезет в экран телефона: {longest}"


def test_optional_question_spread_mentions_skip_button() -> None:
    # У «Трёх карт» вопрос необязателен — в клавиатуре есть «⏭ Пропустить»,
    # и подсказка обязана объяснить, что с ней делать.
    spec = SPREADS[SpreadType.THREE_CARDS]
    assert not spec.question_required
    assert "Пропустить" in spec.question_hint


def test_required_question_spreads_do_not_promise_skip() -> None:
    for spread_type in (SpreadType.WISH, SpreadType.RELATIONSHIP):
        spec = SPREADS[spread_type]
        assert spec.question_required
        assert "Пропустить" not in spec.question_hint
