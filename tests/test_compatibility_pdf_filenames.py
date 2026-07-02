from datetime import datetime
from zoneinfo import ZoneInfo

from astra.compatibility.enums import RelationshipContext
from astra.services.compatibility_pdf_filenames import (
    build_pdf_download_filename,
    sanitize_pdf_filename_stem,
)


def test_sanitize_removes_forbidden_windows_chars() -> None:
    raw = 'Aidamir × Анж: тест? <bad> "path" | file*'
    stem = sanitize_pdf_filename_stem(raw)
    assert ":" not in stem
    assert "?" not in stem
    assert "<" not in stem
    assert "|" not in stem
    assert '"' not in stem
    assert "*" not in stem


def test_build_pdf_download_filename_format() -> None:
    created = datetime(2026, 7, 2, 16, 19, tzinfo=ZoneInfo("Europe/Moscow"))
    name = build_pdf_download_filename(
        person_a_name="Aidamir",
        person_b_name="Анж",
        relationship_context=RelationshipContext.LOVE,
        created_at=created,
        timezone="Europe/Moscow",
    )
    assert name.endswith(".pdf")
    assert "Aidamir" in name
    assert "Анж" in name
    assert "Отношения" in name
    assert "02.07.2026 16-19" in name
    assert "💕" in name
    assert "💑" in name


def test_build_pdf_download_filename_no_forbidden_chars() -> None:
    created = datetime(2026, 7, 2, 16, 19, tzinfo=ZoneInfo("UTC"))
    name = build_pdf_download_filename(
        person_a_name="A/B",
        person_b_name="C:D",
        relationship_context=RelationshipContext.WORK,
        created_at=created,
    )
    assert "/" not in name
    assert ":" not in name
