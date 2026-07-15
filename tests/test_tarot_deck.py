"""Тесты колоды таро: валидность контента 78 карт, честный draw, каркас под игру."""

from collections import Counter

import pytest

from astra.tarot.deck import ARCANA_LABELS_RU, DECK, MAJOR_ARCANA, card_by_id
from astra.tarot.deck_minor import CUPS, PENTACLES, SWORDS, WANDS
from astra.tarot.draw import draw_card, draw_cards

_COURT_IDS = {11: "page", 12: "knight", 13: "queen", 14: "king"}


class TestDeckContent:
    def test_78_cards_total(self):
        assert len(DECK) == 78

    def test_22_major_arcana(self):
        assert len(MAJOR_ARCANA) == 22
        assert [c.number for c in MAJOR_ARCANA] == list(range(22))

    def test_each_suit_has_14_cards(self):
        for suit, cards in {
            "wands": WANDS, "cups": CUPS, "swords": SWORDS, "pentacles": PENTACLES,
        }.items():
            assert len(cards) == 14, suit
            assert [c.number for c in cards] == list(range(1, 15)), suit
            assert all(c.arcana == suit for c in cards), suit

    def test_ids_unique_and_formatted(self):
        ids = [c.id for c in DECK]
        assert len(ids) == len(set(ids))
        for card in MAJOR_ARCANA:
            assert card.id == f"major_{card.number:02d}"
        for card in (*WANDS, *CUPS, *SWORDS, *PENTACLES):
            if card.number <= 10:
                assert card.id == f"{card.arcana}_{card.number:02d}", card.id
            else:
                assert card.id == f"{card.arcana}_{_COURT_IDS[card.number]}", card.id

    def test_content_complete(self):
        for card in DECK:
            assert card.name_ru
            assert card.emoji
            assert len(card.keywords) >= 3
            assert len(card.keywords_reversed) >= 2
            assert card.astro_affinity
            assert len(card.voice) > 30
            assert card.arcana in ARCANA_LABELS_RU
            # картинки лежат по конвенции в images.py, поле не заполняется
            assert card.image_file is None

    def test_major_astro_affinities_are_planets_or_signs(self):
        known = {
            "Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн",
            "Уран", "Нептун", "Плутон",
            "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
            "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
        }
        for card in MAJOR_ARCANA:
            assert card.astro_affinity in known, card.id

    def test_card_by_id(self):
        chariot = card_by_id("major_07")
        assert chariot is not None and chariot.name_ru == "Колесница"
        queen = card_by_id("cups_queen")
        assert queen is not None and queen.name_ru == "Королева Кубков"
        assert card_by_id("major_99") is None


class TestDraw:
    def test_draw_returns_deck_card(self):
        card = draw_card()
        assert card_by_id(card.id) is card

    def test_exclude_respected(self):
        excluded = frozenset(c.id for c in DECK[:-1])
        for _ in range(20):
            assert draw_card(exclude_ids=excluded).id == DECK[-1].id

    def test_exclude_all_falls_back_to_full_deck(self):
        excluded = frozenset(c.id for c in DECK)
        assert draw_card(exclude_ids=excluded) is not None

    def test_distribution_roughly_uniform(self):
        counts = Counter(draw_card().id for _ in range(7800))
        # 78 карт × ~100 вытягиваний; допускаем широкий разброс
        assert len(counts) == 78
        assert all(40 <= n <= 180 for n in counts.values()), counts


class TestDrawCards:
    def test_no_repeats_in_spread(self):
        for _ in range(50):
            drawn = draw_cards(5)
            ids = [d.card.id for d in drawn]
            assert len(ids) == len(set(ids)) == 5

    def test_upright_only_by_default(self):
        assert all(not d.reversed for d in draw_cards(10))

    def test_exclude_respected(self):
        excluded = frozenset(c.id for c in DECK[3:])
        drawn = draw_cards(3, exclude_ids=excluded)
        assert {d.card.id for d in drawn} == {c.id for c in DECK[:3]}

    def test_count_out_of_range_raises(self):
        with pytest.raises(ValueError):
            draw_cards(0)
        with pytest.raises(ValueError):
            draw_cards(79)

    def test_allow_reversed_produces_both_orientations(self):
        drawn = [d for _ in range(30) for d in draw_cards(5, allow_reversed=True)]
        orientations = {d.reversed for d in drawn}
        assert orientations == {True, False}
