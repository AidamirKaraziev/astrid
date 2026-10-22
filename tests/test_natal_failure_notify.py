"""Все три пути падения разбора доводят до человека одно уведомление."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.natal_report.enums import NatalReportStatus
from astra.services import natal_report_service as svc
from astra.services.natal_failure_notify import NATAL_FAILURE_TEXT

TELEGRAM_ID = 424242
SVC = "astra.services.natal_report_service"


def _report(*, llm_output: dict | None) -> MagicMock:
    report = MagicMock()
    report.id = uuid4()
    report.owner_user_id = uuid4()
    report.status = NatalReportStatus.CHART_READY.value
    report.pdf_path = None
    report.llm_output = llm_output
    return report


async def _run(path: str, *, user_found: bool = True) -> tuple[AsyncMock, list[str]]:
    """Прогнать один путь падения; вернуть мок отправки и журнал порядка вызовов."""
    calls: list[str] = []
    report = _report(llm_output={"x": 1} if path == "pdf" else None)

    async def mark_failed(*_a: object, **_k: object) -> None:
        calls.append("mark_failed")

    async def send(*_a: object, **_k: object) -> None:
        calls.append("send")

    send_mock = AsyncMock(side_effect=send)
    user = MagicMock(telegram_id=TELEGRAM_ID) if user_found else None
    patches = [
        patch(f"{SVC}.get_settings", return_value=MagicMock()),
        patch(f"{SVC}.natal_crud.get_natal_report", new=AsyncMock(return_value=report)),
        patch(f"{SVC}.natal_crud.mark_natal_failed", new=AsyncMock(side_effect=mark_failed)),
        patch(f"{SVC}.users_crud.get_user_by_id", new=AsyncMock(return_value=user)),
        patch("astra.services.natal_failure_notify.send_telegram_html", new=send_mock),
    ]
    if path == "pdf":
        patches.append(
            patch(f"{SVC}.FullNatalChart.model_validate", side_effect=ValueError("boom")),
        )
        target = svc.generate_natal_report_pdf
    else:
        deepseek = MagicMock()
        deepseek.is_configured.return_value = True
        patches += [
            patch(f"{SVC}.get_deepseek_provider", return_value=deepseek),
            patch(f"{SVC}._prompt_input_from_report", return_value=MagicMock()),
        ]
        if path == "llm_none":
            gen = AsyncMock(return_value=(None, "bad_json"))
        else:
            gen = AsyncMock(side_effect=RuntimeError("boom"))
        patches.append(patch(f"{SVC}.generate_natal_output", new=gen))
        target = svc.generate_natal_llm

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = await target(MagicMock(), report.id)
    assert result is None
    return send_mock, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["llm_none", "llm_exception", "pdf"])
async def test_failure_path_notifies_person(path: str) -> None:
    send_mock, calls = await _run(path)
    send_mock.assert_awaited_once_with(TELEGRAM_ID, NATAL_FAILURE_TEXT)
    assert calls == ["mark_failed", "send"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["llm_none", "llm_exception", "pdf"])
async def test_failure_path_without_user_stays_silent(path: str) -> None:
    send_mock, calls = await _run(path, user_found=False)
    send_mock.assert_not_awaited()
    assert calls == ["mark_failed"]
