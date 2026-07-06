from enum import StrEnum


class NatalReportStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    CHART_READY = "chart_ready"
    TEXT_READY = "text_ready"
    READY = "ready"
    FAILED = "failed"


NATAL_IN_FLIGHT_STATUSES: frozenset[NatalReportStatus] = frozenset(
    {
        NatalReportStatus.GENERATING,
        NatalReportStatus.CHART_READY,
        NatalReportStatus.TEXT_READY,
    },
)
