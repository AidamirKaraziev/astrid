from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from astra.services.compatibility_service import delete_compatibility_report_for_user


@pytest.mark.asyncio
async def test_delete_compatibility_report_for_user_removes_pdf_and_db_row(tmp_path: Path) -> None:
    owner_id = uuid4()
    report_id = uuid4()
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    report = MagicMock()
    report.owner_user_id = owner_id
    report.pdf_path = str(pdf_path)

    session = AsyncMock()

    with (
        patch(
            "astra.services.compatibility_service.compatibility_crud.get_compatibility_report",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "astra.services.compatibility_service.users_crud.get_user_by_id",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "astra.telegram.progress.clear_progress_message_id",
            new=AsyncMock(),
        ),
        patch(
            "astra.services.compatibility_service.compatibility_crud.delete_compatibility_report",
            new=AsyncMock(return_value=True),
        ),
    ):
        ok = await delete_compatibility_report_for_user(session, report_id, owner_id)

    assert ok is True
    assert not pdf_path.exists()


@pytest.mark.asyncio
async def test_delete_compatibility_report_for_user_wrong_owner() -> None:
    report = MagicMock()
    report.owner_user_id = uuid4()
    session = AsyncMock()

    with patch(
        "astra.services.compatibility_service.compatibility_crud.get_compatibility_report",
        new=AsyncMock(return_value=report),
    ):
        ok = await delete_compatibility_report_for_user(session, uuid4(), uuid4())

    assert ok is False
