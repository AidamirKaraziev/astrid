"""Сбой на любом пути натала и совместимости доводит до человека ровно одно сообщение.

Сервисы гоняются настоящие, а уведомление ловится на самой отправке
(`send_telegram_html`): так видно и пропуск, и дубль.
"""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.compatibility.enums import ReportStatus
from astra.messaging.schemas import TaskMessage, TaskType
from astra.natal_report.enums import NatalReportStatus
from astra.services.compatibility_failure_notify import COMPATIBILITY_FAILURE_TEXT
from astra.services.natal_failure_notify import NATAL_FAILURE_TEXT
from astra.workers import handlers

TELEGRAM_ID = 424242
NAT = "astra.services.natal_report_service"
COM = "astra.services.compatibility_service"

NATAL_PATHS = [
    ("deepseek_disabled", "generate"),
    ("llm_none", "generate"),
    ("llm_exception", "generate"),
    ("missing_llm_output", "pdf"),
    ("pdf_exception", "pdf"),
]
COMPAT_PATHS = [
    ("deepseek_disabled", "generate"),
    ("llm_none", "generate"),
    ("llm_exception", "generate"),
    ("missing_llm_output", "pdf"),
    ("pdf_exception", "pdf"),
    ("pdf_missing", "send"),
]


def _task(report_id):
    return TaskMessage(type=TaskType.NATAL_GENERATE, report_id=report_id)


def _deepseek(configured: bool) -> MagicMock:
    deepseek = MagicMock()
    deepseek.is_configured.return_value = configured
    return deepseek


async def _run_natal(path: str, stage: str, *, user_found: bool = True) -> AsyncMock:
    report = SimpleNamespace(
        id=uuid4(),
        owner_user_id=uuid4(),
        status=NatalReportStatus.CHART_READY.value,
        pdf_path=None,
        llm_output={"x": 1} if path == "pdf_exception" else None,
    )

    async def mark_failed(_s, rep, _reason):
        rep.status = NatalReportStatus.FAILED.value

    send = AsyncMock()
    user = SimpleNamespace(telegram_id=TELEGRAM_ID, id=uuid4()) if user_found else None
    patches = [
        patch(f"{NAT}.get_settings", return_value=MagicMock()),
        patch(f"{NAT}.natal_crud.get_natal_report", new=AsyncMock(return_value=report)),
        patch(f"{NAT}.natal_crud.mark_natal_failed", new=AsyncMock(side_effect=mark_failed)),
        patch("astra.workers.handlers.users_crud.get_user_by_id", new=AsyncMock(return_value=user)),
        patch("astra.workers.handlers.send_chat_action_typing", new=AsyncMock()),
        patch("astra.services.natal_failure_notify.send_telegram_html", new=send),
    ]
    if stage == "pdf":
        if path == "pdf_exception":
            patches.append(patch(f"{NAT}.FullNatalChart.model_validate", side_effect=ValueError("boom")))
        handler = handlers.handle_natal_pdf_generate
    else:
        patches += [
            patch(f"{NAT}.get_deepseek_provider", return_value=_deepseek(path != "deepseek_disabled")),
            patch(f"{NAT}._prompt_input_from_report", return_value=MagicMock()),
        ]
        if path == "llm_none":
            gen = AsyncMock(return_value=(None, "bad_json"))
        else:
            gen = AsyncMock(side_effect=RuntimeError("boom"))
        patches.append(patch(f"{NAT}.generate_natal_output", new=gen))
        handler = handlers.handle_natal_generate
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await handler(MagicMock(commit=AsyncMock()), _task(report.id))
    return send


async def _run_compat(path: str, stage: str, tmp_path: Path, *, user_found: bool = True) -> AsyncMock:
    report = SimpleNamespace(
        id=uuid4(),
        owner_user_id=uuid4(),
        status=ReportStatus.READY if path == "pdf_missing" else ReportStatus.SYNASTRY_READY,
        pdf_path=str(tmp_path / "nope.pdf") if path == "pdf_missing" else None,
        sent_at=None,
        llm_output={"x": 1} if path == "pdf_exception" else None,
    )

    async def mark_failed(_s, rep, _reason):
        rep.status = ReportStatus.FAILED

    send = AsyncMock()
    user = SimpleNamespace(telegram_id=TELEGRAM_ID, id=uuid4()) if user_found else None
    patches = [
        patch(f"{COM}.get_settings", return_value=MagicMock()),
        patch(f"{COM}.compatibility_crud.get_compatibility_report", new=AsyncMock(return_value=report)),
        patch(f"{COM}.compatibility_crud.mark_report_failed", new=AsyncMock(side_effect=mark_failed)),
        patch(f"{COM}.users_crud.get_user_by_id", new=AsyncMock(return_value=user)),
        patch("astra.workers.handlers.users_crud.get_user_by_id", new=AsyncMock(return_value=user)),
        patch("astra.workers.handlers.send_chat_action_typing", new=AsyncMock()),
        patch("astra.workers.handlers.clear_progress", new=AsyncMock()),
        patch("astra.services.compatibility_failure_notify.send_telegram_html", new=send),
    ]
    if stage == "send":
        handler = handlers.handle_compatibility_send
    elif stage == "pdf":
        if path == "pdf_exception":
            patches.append(
                patch(f"{COM}.build_prompt_input_from_report", new=AsyncMock(side_effect=ValueError("boom"))),
            )
        handler = handlers.handle_pdf_generate
    else:
        patches += [
            patch(f"{COM}.get_deepseek_provider", return_value=_deepseek(path != "deepseek_disabled")),
            patch(f"{COM}.build_prompt_input_from_report", new=AsyncMock(return_value=MagicMock())),
        ]
        if path == "llm_none":
            gen = AsyncMock(return_value=(None, "bad_json"))
        else:
            gen = AsyncMock(side_effect=RuntimeError("boom"))
        patches.append(patch(f"{COM}.generate_compatibility_output", new=gen))
        handler = handlers.handle_compatibility_generate
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await handler(MagicMock(commit=AsyncMock()), _task(report.id))
    return send


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "stage"), NATAL_PATHS)
async def test_natal_failure_notifies_exactly_once(path: str, stage: str) -> None:
    send = await _run_natal(path, stage)
    send.assert_awaited_once_with(TELEGRAM_ID, NATAL_FAILURE_TEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "stage"), COMPAT_PATHS)
async def test_compatibility_failure_notifies_exactly_once(path: str, stage: str, tmp_path: Path) -> None:
    send = await _run_compat(path, stage, tmp_path)
    send.assert_awaited_once_with(TELEGRAM_ID, COMPATIBILITY_FAILURE_TEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "stage"), NATAL_PATHS)
async def test_natal_failure_without_user_stays_silent(path: str, stage: str) -> None:
    send = await _run_natal(path, stage, user_found=False)
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "stage"), COMPAT_PATHS)
async def test_compatibility_failure_without_user_stays_silent(path: str, stage: str, tmp_path: Path) -> None:
    send = await _run_compat(path, stage, tmp_path, user_found=False)
    send.assert_not_awaited()
