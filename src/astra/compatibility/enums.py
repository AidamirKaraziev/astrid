from enum import StrEnum


class RelationshipContext(StrEnum):
    LOVE = "love"
    WORK = "work"
    FRIENDSHIP = "friendship"


class PairMode(StrEnum):
    ME_PARTNER = "me_partner"
    TWO_PEOPLE = "two_people"


class ReportStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


RELATIONSHIP_LABELS: dict[RelationshipContext, str] = {
    RelationshipContext.LOVE: "💑 Отношения",
    RelationshipContext.WORK: "💼 Работа",
    RelationshipContext.FRIENDSHIP: "🤝 Дружба",
}

PAIR_MODE_LABELS: dict[PairMode, str] = {
    PairMode.ME_PARTNER: "Я + он/она",
    PairMode.TWO_PEOPLE: "Он + она",
}
