"""Человекочитаемые имена PDF совместимости, безопасные для файловых систем."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astra.compatibility.enums import (
    RELATIONSHIP_EMOJI,
    RELATIONSHIP_LABELS,
    RelationshipContext,
)
from astra.compatibility.models import CompatibilityReport

_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_MAX_STEM_LEN = 180
_WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    },
)


def sanitize_pdf_filename_stem(raw: str) -> str:
    """Убрать символы, недопустимые в Windows/macOS/Linux, сохранить кириллицу и эмодзи."""
    text = unicodedata.normalize("NFKC", raw.strip())
    text = _FORBIDDEN_CHARS.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip(" .")
    if not text:
        return "совместимость"
    if text.upper() in _WINDOWS_RESERVED:
        text = f"_{text}"
    if len(text) > _MAX_STEM_LEN:
        text = text[:_MAX_STEM_LEN].rstrip(" .")
    return text


def build_pdf_download_filename(
    *,
    person_a_name: str,
    person_b_name: str,
    relationship_context: RelationshipContext,
    created_at: datetime,
    timezone: str = "Europe/Moscow",
) -> str:
    """Имя файла для скачивания: «♥️ Имя × Имя · Отношения · 02.07.2026 16-19»."""
    emoji = RELATIONSHIP_EMOJI.get(relationship_context, "✨")
    ctx_label = RELATIONSHIP_LABELS.get(relationship_context, str(relationship_context))
    local_time = created_at.astimezone(ZoneInfo(timezone))
    ts = local_time.strftime("%d.%m.%Y %H-%M")
    raw = f"{emoji} {person_a_name.strip()} × {person_b_name.strip()} · {ctx_label} · {ts}"
    stem = sanitize_pdf_filename_stem(raw)
    return f"{stem}.pdf"


def build_pdf_download_filename_from_report(report: CompatibilityReport) -> str:
    name_a = str(report.person_a_snapshot.get("name") or "—")
    name_b = str(report.person_b_snapshot.get("name") or "—")
    tz = str(report.person_a_snapshot.get("timezone") or "Europe/Moscow")
    created = report.created_at or datetime.now(tz=ZoneInfo("UTC"))
    context = RelationshipContext(report.relationship_context)
    return build_pdf_download_filename(
        person_a_name=name_a,
        person_b_name=name_b,
        relationship_context=context,
        created_at=created,
        timezone=tz,
    )


def pdf_path_for_report_file(
    base_dir: Path,
    filename: str,
    report_id: uuid.UUID,
) -> Path:
    """Путь на диске; при коллизии добавляет короткий суффикс id."""
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    return base_dir / f"{stem} ({report_id.hex[:8]}){suffix}"
