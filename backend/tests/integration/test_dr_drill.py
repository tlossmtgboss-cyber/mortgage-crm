"""Integration tests for the DR drill driver.

Exercises ``backend/scripts/dr_drill.py`` end-to-end against the SQLite
target so CI always runs the full backup -> drop -> restore -> verify
loop.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_dr_drill():
    target = _BACKEND_DIR / "scripts" / "dr_drill.py"
    if not target.exists():
        pytest.skip("dr_drill.py not found")
    spec = importlib.util.spec_from_file_location("_perennia_dr_drill", str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"dr_drill import failed: {exc}")
    return module


_drill = _load_dr_drill()


def test_drill_runs_against_sqlite(tmp_path):
    """The drill must complete successfully against the SQLite target."""
    report_dir = tmp_path / "dr_drills"
    report = _drill.run_drill("sqlite", report_dir)
    assert report["success"] is True, report
    assert report["target"] == "sqlite"
    assert report["rto_seconds"] >= 0


def test_drill_produces_json_report(tmp_path):
    """A JSON report must be written to ``report_dir`` after each run."""
    report_dir = tmp_path / "dr_drills"
    report = _drill.run_drill("sqlite", report_dir)
    report_path = Path(report["report_path"])
    assert report_path.exists(), "drill must persist its report to disk"
    parsed = json.loads(report_path.read_text())
    assert parsed["target"] == "sqlite"
    for field in ("start_time", "end_time", "rto_seconds", "success"):
        assert field in parsed, f"report missing {field}"


def test_drill_row_count_parity(tmp_path):
    """Row counts in the restored DB must match the baseline exactly."""
    report_dir = tmp_path / "dr_drills"
    report = _drill.run_drill("sqlite", report_dir)
    deltas = report.get("row_count_deltas", {})
    # Every table delta must be zero — restore is lossless.
    assert deltas, "report must include row_count_deltas"
    for table, delta in deltas.items():
        assert delta == 0, f"row delta for {table} was {delta}, expected 0"
    # Sanity: baseline matches restored.
    assert report["baseline_total_rows"] == report["restored_total_rows"]
