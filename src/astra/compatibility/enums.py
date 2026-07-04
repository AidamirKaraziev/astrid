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
    SYNASTRY_READY = "synastry_ready"
    TEXT_READY = "text_ready"
    READY = "ready"
    FAILED = "failed"


COMPATIBILITY_IN_FLIGHT_STATUSES: frozenset[ReportStatus] = frozenset(
    {
        ReportStatus.GENERATING,
        ReportStatus.SYNASTRY_READY,
        ReportStatus.TEXT_READY,
    },
)


RELATIONSHIP_LABELS: dict[RelationshipContext, str] = {
    RelationshipContext.LOVE: "💑 Отношения",
    RelationshipContext.WORK: "💼 Работа",
    RelationshipContext.FRIENDSHIP: "🤝 Дружба",
}

PAIR_MODE_LABELS: dict[PairMode, str] = {
    PairMode.ME_PARTNER: "Моя совместимость",
    PairMode.TWO_PEOPLE: "Другая пара",
}
