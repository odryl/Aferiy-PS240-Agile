"""Tests for bounded Agile JSONL shadow-log rotation."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "aecc_battery" / "agile_export.py"
SPEC = importlib.util.spec_from_file_location("aecc_agile_export_test_module", MODULE_PATH)
assert SPEC and SPEC.loader
EXPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXPORT
SPEC.loader.exec_module(EXPORT)


def test_export_rotates_and_compresses_an_oversized_segment(tmp_path: Path) -> None:
    export_path = tmp_path / "aecc_battery_agile_plan_export.jsonl"
    old_record = {"schema_version": 2, "label": "old"}
    export_path.write_text(json.dumps(old_record) + "\n", encoding="utf-8")

    result = EXPORT.append_agile_json_line(
        str(export_path),
        {"schema_version": 3, "label": "new"},
        max_bytes=1,
    )

    active = [json.loads(line) for line in export_path.read_text().splitlines()]
    archives = list(tmp_path.glob("aecc_battery_agile_plan_export-*.jsonl.gz"))
    assert active == [{"schema_version": 3, "label": "new"}]
    assert len(archives) == 1
    with gzip.open(archives[0], "rt", encoding="utf-8") as archive:
        assert [json.loads(line) for line in archive] == [old_record]
    assert result["rotated_archive"] == archives[0].name
    assert result["rotation_threshold_bytes"] == 1
