"""Реестр продуктов таро: каждый расклад — свой промпт, схема и формат."""

from astra.llm.prompts.tarot_spreads.base import TarotProduct
from astra.llm.prompts.tarot_spreads.relationship import RelationshipProduct
from astra.llm.prompts.tarot_spreads.three_cards import ThreeCardsProduct
from astra.llm.prompts.tarot_spreads.wish import WishProduct
from astra.tarot.spreads import SpreadType

TAROT_PRODUCTS: dict[SpreadType, TarotProduct] = {
    SpreadType.WISH: WishProduct(),
    SpreadType.THREE_CARDS: ThreeCardsProduct(),
    SpreadType.RELATIONSHIP: RelationshipProduct(),
}

__all__ = ["TarotProduct", "TAROT_PRODUCTS"]
