"""Pure JSONL export rotation helpers for Agile shadow logging."""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AGILE_PLAN_EXPORT_MAX_BYTES = 8 * 1024 * 1024


def append_agile_json_line(
    path: str,
    record: dict[str, Any],
    *,
    max_bytes: int = AGILE_PLAN_EXPORT_MAX_BYTES,
) -> dict[str, Any]:
    """Rotate and gzip an oversized segment, then append one JSON record."""
    export_path = Path(path)
    rotated_archive: str | None = None
    if export_path.exists() and export_path.stat().st_size >= max_bytes:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        rotated_path = export_path.with_name(f"{export_path.stem}-{stamp}.jsonl")
        archive_path = Path(f"{rotated_path}.gz")
        temporary_archive = Path(f"{archive_path}.tmp")
        export_path.replace(rotated_path)
        try:
            with rotated_path.open("rb") as source, gzip.open(temporary_archive, "wb") as target:
                shutil.copyfileobj(source, target)
            temporary_archive.replace(archive_path)
            rotated_path.unlink()
            rotated_archive = archive_path.name
        except OSError:
            temporary_archive.unlink(missing_ok=True)
            if rotated_path.exists() and not export_path.exists():
                rotated_path.replace(export_path)
            raise

    with export_path.open("a", encoding="utf-8") as export_file:
        export_file.write(json.dumps(record, default=str, separators=(",", ":")))
        export_file.write("\n")
    return {
        "file_size_bytes": export_path.stat().st_size,
        "rotated_archive": rotated_archive,
        "rotation_threshold_bytes": max_bytes,
    }
