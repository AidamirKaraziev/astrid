"""Реестр продуктов таро: каждый расклад — свой промпт, схема и формат."""

from astra.llm.prompts.tarot_spreads.base import TarotProduct
from astra.llm.prompts.tarot_spreads.relationship import RelationshipProduct
from astra.llm.prompts.tarot_spreads.three_cards import ThreeCardsProduct
from astra.llm.prompts.tarot_spreads.yes_no import YesNoProduct
from astra.tarot.spreads import SpreadType

TAROT_PRODUCTS: dict[SpreadType, TarotProduct] = {
    SpreadType.YES_NO: YesNoProduct(),
    SpreadType.THREE_CARDS: ThreeCardsProduct(),
    SpreadType.RELATIONSHIP: RelationshipProduct(),
}

__all__ = ["TarotProduct", "TAROT_PRODUCTS"]
