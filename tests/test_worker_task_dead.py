"""handle_task_dead: задача исчерпала попытки — деньги вернулись, человек узнал, ничего не бросает."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from astra.ask.enums import AskStatus
from astra.compatibility.enums import ReportStatus
from astra.messaging.schemas import TaskMessage, TaskType
from astra.natal_report.enums import NatalReportStatus
from astra.predictions.status import PredictionStatus
from astra.tarot.enums import ReadingStatus
from astra.workers import handlers

pytestmark = pytest.mark.anyio

TG = 777
DAY = date(2026, 6, 14)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), telegram_id=TG, profile=SimpleNamespace(timezone="UTC"))


# --- таро ---------------------------------------------------------------


@pytest.mark.parametrize("ttype", [TaskType.TAROT_READING_GENERATE, TaskType.TAROT_READING_SEND])
async def test_tarot_dead_refunds_and_notifies(ttype: TaskType) -> None:
    user = _user()
    reading = SimpleNamespace(
        id=uuid4(), user_id=user.id, status=ReadingStatus.GENERATING, sent_at=None
    )
    task = TaskMessage(type=ttype, reading_id=reading.id)
    session = AsyncMock()
    with (
        patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
        patch("astra.workers.handlers.users_crud.get_user_by_id", AsyncMock(return_value=user)),
        patch(
            "astra.payments.models.get_completed_payment_for_reading",
            AsyncMock(side_effect=[object(), None]),
        ),
        patch(
            "astra.services.wallet_service.has_unrefunded_purchase",
            AsyncMock(return_value=False),
        ),
        patch(
            "astra.payments.service.refund_reading_payment", AsyncMock(return_value=True)
        ) as refund,
        patch("astra.workers.handlers.notify_reading_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(session, task)

    refund.assert_called_once_with(session, reading, TG)
    notify.assert_called_once_with(session, reading, refunded=True)
    assert reading.status == ReadingStatus.FAILED
    session.commit.assert_awaited()


def _tarot_failed_run(payments: list, wallet_pending: bool):
    user = _user()
    reading = SimpleNamespace(id=uuid4(), user_id=user.id, status=ReadingStatus.FAILED, sent_at=None)
    task = TaskMessage(type=TaskType.TAROT_READING_GENERATE, reading_id=reading.id)
    patches = (
        patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
        patch("astra.workers.handlers.users_crud.get_user_by_id", AsyncMock(return_value=user)),
        patch(
            "astra.payments.models.get_completed_payment_for_reading",
            AsyncMock(side_effect=payments),
        ),
        patch(
            "astra.services.wallet_service.has_unrefunded_purchase",
            AsyncMock(return_value=wallet_pending),
        ),
        patch("astra.payments.service.refund_reading_payment", AsyncMock(return_value=False)),
        patch("astra.workers.handlers.notify_reading_failed", AsyncMock()),
    )
    return task, reading, patches


async def test_tarot_dead_repeat_after_full_refund_sends_nothing() -> None:
    task, _reading, (p1, p2, p3, p4, p5, p6) = _tarot_failed_run([None], False)
    with p1, p2, p3, p4, p5 as refund, p6 as notify:
        await handlers.handle_task_dead(AsyncMock(), task)
    refund.assert_not_called()
    notify.assert_not_called()


async def test_tarot_dead_repeat_after_partial_refund_sends_truthful_text() -> None:
    # Telegram упал: платёж остаётся completed и до, и после попытки возврата.
    task, reading, (p1, p2, p3, p4, p5, p6) = _tarot_failed_run([object(), object()], False)
    session = AsyncMock()
    with p1, p2, p3, p4, p5 as refund, p6 as notify:
        await handlers.handle_task_dead(session, task)
    refund.assert_called_once()
    notify.assert_called_once_with(session, reading, refunded=False)


async def test_tarot_dead_delivered_does_nothing() -> None:
    reading = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), status=ReadingStatus.READY, sent_at=datetime.now(UTC)
    )
    task = TaskMessage(type=TaskType.TAROT_READING_SEND, reading_id=reading.id)
    with (
        patch("astra.tarot.models.get_reading", AsyncMock(return_value=reading)),
        patch("astra.payments.service.refund_reading_payment", AsyncMock()) as refund,
        patch("astra.workers.handlers.notify_reading_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(AsyncMock(), task)
    refund.assert_not_called()
    notify.assert_not_called()


# --- «Спроси» -----------------------------------------------------------


async def test_ask_dead_refunds_and_notifies() -> None:
    user = _user()
    reading = SimpleNamespace(
        id=uuid4(), user_id=user.id, status=AskStatus.GENERATING, refunded=False
    )
    task = TaskMessage(type=TaskType.ASK_ANSWER_GENERATE, reading_id=reading.id)
    session = AsyncMock()
    with (
        patch("astra.ask.models.get_reading", AsyncMock(return_value=reading)),
        patch("astra.ask.models.mark_failed", AsyncMock()) as mark_failed,
        patch("astra.workers.handlers.users_crud.get_user_by_id", AsyncMock(return_value=user)),
        patch(
            "astra.services.ask_service.refund_ask_payment", AsyncMock(return_value=True)
        ) as refund,
        patch("astra.services.ask_service.notify_ask_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(session, task)
    refund.assert_called_once_with(session, reading, TG)
    mark_failed.assert_called_once()
    notify.assert_called_once_with(session, reading, refunded=True)


@pytest.mark.parametrize(
    ("status", "refunded"),
    [(AskStatus.READY, False), (AskStatus.FAILED, True)],
)
async def test_ask_dead_delivered_or_already_refunded_does_nothing(
    status: AskStatus, refunded: bool
) -> None:
    reading = SimpleNamespace(id=uuid4(), user_id=uuid4(), status=status, refunded=refunded)
    task = TaskMessage(type=TaskType.ASK_ANSWER_GENERATE, reading_id=reading.id)
    with (
        patch("astra.ask.models.get_reading", AsyncMock(return_value=reading)),
        patch("astra.services.ask_service.refund_ask_payment", AsyncMock()) as refund,
        patch("astra.services.ask_service.notify_ask_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(AsyncMock(), task)
    refund.assert_not_called()
    notify.assert_not_called()


# --- натал и совместимость ------------------------------------------------

NATAL_TYPES = [TaskType.NATAL_GENERATE, TaskType.NATAL_PDF_GENERATE, TaskType.NATAL_SEND]
COMPAT_TYPES = [
    TaskType.SYNASTRY_BUILD,
    TaskType.COMPATIBILITY_GENERATE,
    TaskType.PDF_GENERATE,
    TaskType.COMPATIBILITY_SEND,
]


@pytest.mark.parametrize("ttype", NATAL_TYPES)
async def test_natal_dead_marks_failed_and_notifies(ttype: TaskType) -> None:
    report = SimpleNamespace(
        id=uuid4(), owner_user_id=uuid4(), status=NatalReportStatus.TEXT_READY, sent_at=None
    )
    task = TaskMessage(type=ttype, report_id=report.id)
    session = AsyncMock()
    with (
        patch("astra.natal_report.crud.get_natal_report", AsyncMock(return_value=report)),
        patch("astra.natal_report.crud.mark_natal_failed", AsyncMock()) as mark,
        patch("astra.workers.handlers._notify_failure_if_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(session, task)
    mark.assert_called_once()
    notify.assert_called_once_with(session, report.id, owner_of="natal")


@pytest.mark.parametrize("ttype", COMPAT_TYPES)
async def test_compatibility_dead_marks_failed_and_notifies(ttype: TaskType) -> None:
    report = SimpleNamespace(
        id=uuid4(), owner_user_id=uuid4(), status=ReportStatus.GENERATING, sent_at=None
    )
    task = TaskMessage(type=ttype, report_id=report.id)
    session = AsyncMock()
    with (
        patch("astra.compatibility.crud.get_compatibility_report", AsyncMock(return_value=report)),
        patch("astra.compatibility.crud.mark_report_failed", AsyncMock()) as mark,
        patch("astra.workers.handlers._notify_failure_if_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(session, task)
    mark.assert_called_once()
    notify.assert_called_once_with(session, report.id, owner_of="compatibility")


@pytest.mark.parametrize(
    ("status", "sent_at"),
    [(NatalReportStatus.FAILED, None), (NatalReportStatus.READY, datetime.now(UTC))],
)
async def test_natal_dead_failed_or_delivered_does_nothing(
    status: NatalReportStatus, sent_at: datetime | None
) -> None:
    report = SimpleNamespace(id=uuid4(), owner_user_id=uuid4(), status=status, sent_at=sent_at)
    task = TaskMessage(type=TaskType.NATAL_SEND, report_id=report.id)
    with (
        patch("astra.natal_report.crud.get_natal_report", AsyncMock(return_value=report)),
        patch("astra.natal_report.crud.mark_natal_failed", AsyncMock()) as mark,
        patch("astra.workers.handlers._notify_failure_if_failed", AsyncMock()) as notify,
    ):
        await handlers.handle_task_dead(AsyncMock(), task)
    mark.assert_not_called()
    notify.assert_not_called()


# --- предсказания -----------------------------------------------------------


@pytest.mark.parametrize(
    "ttype",
    [TaskType.PREDICTION_GENERATE, TaskType.PREDICTION_SEND, TaskType.DAY_CARD_SEND],
)
async def test_prediction_dead_notifies_marks_failed_clears_pending(ttype: TaskType) -> None:
    user = _user()
    prediction = SimpleNamespace(sent_at=None, status=PredictionStatus.TEXT_READY)
    task = TaskMessage(type=ttype, user_id=user.id, prediction_date=DAY)
    with (
        patch("astra.workers.handlers.users_crud.get_user_by_id", AsyncMock(return_value=user)),
        patch(
            "astra.workers.handlers.predictions_crud.get_prediction_for_date",
            AsyncMock(return_value=prediction),
        ),
        patch("astra.workers.handlers.send_final_failure_notification", AsyncMock()) as notify,
        patch("astra.workers.handlers.mark_prediction_failed", AsyncMock()) as mark,
        patch("astra.workers.handlers.clear_prediction_pending", AsyncMock()) as clear,
    ):
        await handlers.handle_task_dead(AsyncMock(), task)
    notify.assert_called_once_with(TG)
    mark.assert_called_once()
    clear.assert_called_once_with(user.id, DAY)


async def test_prediction_dead_already_sent_does_nothing() -> None:
    user = _user()
    prediction = SimpleNamespace(sent_at=datetime.now(UTC), status=PredictionStatus.SENT)
    task = TaskMessage(type=TaskType.PREDICTION_SEND, user_id=user.id, prediction_date=DAY)
    with (
        patch("astra.workers.handlers.users_crud.get_user_by_id", AsyncMock(return_value=user)),
        patch(
            "astra.workers.handlers.predictions_crud.get_prediction_for_date",
            AsyncMock(return_value=prediction),
        ),
        patch("astra.workers.handlers.send_final_failure_notification", AsyncMock()) as notify,
        patch("astra.workers.handlers.mark_prediction_failed", AsyncMock()) as mark,
    ):
        await handlers.handle_task_dead(AsyncMock(), task)
    notify.assert_not_called()
    mark.assert_not_called()


# --- только лог ---------------------------------------------------------------


@pytest.mark.parametrize(
    "ttype",
    [TaskType.BROADCAST_SEND, TaskType.NATAL_CHART_GENERATE, TaskType.DAILY_CONTEXT_BUILD],
)
async def test_log_only_types_touch_nothing(ttype: TaskType) -> None:
    task = TaskMessage(type=ttype, user_id=uuid4(), report_id=uuid4())
    session = AsyncMock()
    with (
        patch("astra.workers.handlers.send_final_failure_notification", AsyncMock()) as notify,
        patch("astra.workers.handlers._notify_failure_if_failed", AsyncMock()) as notify2,
    ):
        await handlers.handle_task_dead(session, task)
    notify.assert_not_called()
    notify2.assert_not_called()
    session.commit.assert_not_called()


# --- не бросает ---------------------------------------------------------------


@pytest.mark.parametrize("ttype", list(TaskType))
async def test_dead_never_raises_even_if_everything_fails(ttype: TaskType) -> None:
    boom = AsyncMock(side_effect=RuntimeError("boom"))
    task = TaskMessage(type=ttype, user_id=uuid4(), report_id=uuid4(), reading_id=uuid4())
    session = AsyncMock()
    session.commit = boom
    session.execute = boom
    session.get = boom
    with (
        patch("astra.workers.handlers.users_crud.get_user_by_id", boom),
        patch("astra.tarot.models.get_reading", boom),
        patch("astra.ask.models.get_reading", boom),
        patch("astra.natal_report.crud.get_natal_report", boom),
        patch("astra.compatibility.crud.get_compatibility_report", boom),
        patch("astra.workers.handlers.predictions_crud.get_prediction_for_date", boom),
    ):
        await handlers.handle_task_dead(session, task)
