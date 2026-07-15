"""Вытягивание карт: криптографический рандом, без подкруток."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from astra.tarot.deck import DECK, TarotCard


@dataclass(frozen=True, slots=True)
class DrawnCard:
    card: TarotCard
    reversed: bool = False  # механика перевёрнутых — этап 2 (allow_reversed)


def draw_card(*, exclude_ids: frozenset[str] = frozenset()) -> TarotCard:
    """Случайная карта из колоды.

    exclude_ids — например, вчерашняя карта, чтобы не повторяться два дня подряд.
    """
    pool = [card for card in DECK if card.id not in exclude_ids]
    if not pool:
        pool = list(DECK)
    return pool[secrets.randbelow(len(pool))]


def draw_cards(
    count: int,
    *,
    exclude_ids: frozenset[str] = frozenset(),
    allow_reversed: bool = False,
) -> list[DrawnCard]:
    """count карт без повторов — расклад из одной колоды."""
    pool = [card for card in DECK if card.id not in exclude_ids]
    if count < 1 or count > len(pool):
        raise ValueError(f"нельзя вытянуть {count} карт из пула {len(pool)}")
    drawn: list[DrawnCard] = []
    for _ in range(count):
        card = pool.pop(secrets.randbelow(len(pool)))
        is_reversed = allow_reversed and secrets.randbelow(2) == 1
        drawn.append(DrawnCard(card=card, reversed=is_reversed))
    return drawn
