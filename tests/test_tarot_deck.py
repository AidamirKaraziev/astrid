"""Тесты колоды таро: валидность контента, честный draw, каркас под игру."""

from collections import Counter

from astra.tarot.deck import ARCANA_LABELS_RU, DECK, MAJOR_ARCANA, card_by_id
from astra.tarot.draw import draw_card


class TestDeckContent:
    def test_22_major_arcana(self):
        assert len(MAJOR_ARCANA) == 22
        assert [c.number for c in MAJOR_ARCANA] == list(range(22))

    def test_ids_unique_and_formatted(self):
        ids = [c.id for c in DECK]
        assert len(ids) == len(set(ids))
        for card in MAJOR_ARCANA:
            assert card.id == f"major_{card.number:02d}"

    def test_content_complete(self):
        for card in DECK:
            assert card.name_ru
            assert card.emoji
            assert len(card.keywords) >= 3
            assert card.astro_affinity
            assert len(card.voice) > 30
            assert card.arcana in ARCANA_LABELS_RU
            # v1: перевёрнутые не заполнены, картинок нет
            assert card.keywords_reversed == ()
            assert card.image_file is None

    def test_astro_affinities_are_planets_or_signs(self):
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
        counts = Counter(draw_card().id for _ in range(2200))
        # 22 карты × ~100 вытягиваний; допускаем широкий разброс
        assert len(counts) == 22
        assert all(40 <= n <= 180 for n in counts.values()), counts
