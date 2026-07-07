"""Вытягивание карты: криптографический рандом, без подкруток."""

from __future__ import annotations

import secrets

from astra.tarot.deck import DECK, TarotCard


def draw_card(*, exclude_ids: frozenset[str] = frozenset()) -> TarotCard:
    """Случайная карта из заполненной части колоды.

    v1: только прямое положение (reversed не используется).
    exclude_ids — например, вчерашняя карта, чтобы не повторяться два дня подряд.
    """
    pool = [card for card in DECK if card.id not in exclude_ids]
    if not pool:
        pool = list(DECK)
    return pool[secrets.randbelow(len(pool))]
