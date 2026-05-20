"""
Integration tests for LOS (Encompass) integration mapping and conflict resolution.

Covers:
  - LOSFieldMapping data class
  - DEFAULT_FIELD_MAPPINGS shape + key fields
  - LOSConfig defaults
  - LOSSyncStatus / LOSSyncDirection enums
  - LOSSyncResult.latency_ms property
  - ConflictDetector strategies: crm_wins, los_wins, newest_wins, manual
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


try:
    from services.los_integration.base import (
        LOSConfig,
        LOSFieldMapping,
        LOSSyncResult,
        LOSSyncStatus,
        LOSSyncDirection,
    )
    from services.los_integration.sync_service import (
        ConflictDetector,
        DEFAULT_FIELD_MAPPINGS,
    )
except Exception as e:
    pytest.skip(f"los_integration not importable: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_los_sync_status_success_value():
    assert LOSSyncStatus.SUCCESS == "success"


def test_los_sync_status_conflict_present():
    assert LOSSyncStatus.CONFLICT.value == "conflict"


def test_los_sync_direction_bidirectional():
    assert LOSSyncDirection.BIDIRECTIONAL.value == "bidirectional"


# ---------------------------------------------------------------------------
# LOSConfig defaults
# ---------------------------------------------------------------------------

def test_los_config_defaults():
    cfg = LOSConfig(
        provider="encompass",
        instance_id="inst1",
        client_id="c",
        client_secret="s",
    )
    assert cfg.enabled is True
    assert cfg.timeout_seconds == 30
    assert cfg.max_retries == 3
    assert cfg.conflict_resolution == "crm_wins"
    assert cfg.sync_interval_minutes == 15


# ---------------------------------------------------------------------------
# LOSFieldMapping
# ---------------------------------------------------------------------------

def test_los_field_mapping_default_bidirectional():
    m = LOSFieldMapping("loan_amount", "Fields/1109")
    assert m.direction == "bidirectional"
    assert m.required is False


def test_default_field_mappings_have_amount():
    names = {m.crm_field for m in DEFAULT_FIELD_MAPPINGS}
    assert "amount" in names
    assert "loan_number" in names
    assert "borrower_email" in names


def test_default_field_mappings_loan_number_pull_only():
    m = next(m for m in DEFAULT_FIELD_MAPPINGS if m.crm_field == "loan_number")
    assert m.direction == "pull"
    assert m.required is True


def test_default_field_mappings_funded_date_los_field():
    m = next(m for m in DEFAULT_FIELD_MAPPINGS if m.crm_field == "funded_date")
    assert m.los_field == "Fields/2370"
    assert m.direction == "pull"


# ---------------------------------------------------------------------------
# LOSSyncResult.latency_ms
# ---------------------------------------------------------------------------

def test_sync_result_latency_ms_computed():
    started = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
    completed = started + timedelta(milliseconds=250)
    r = LOSSyncResult(
        status=LOSSyncStatus.SUCCESS,
        direction=LOSSyncDirection.PUSH,
        loan_id=1,
        started_at=started,
        completed_at=completed,
    )
    assert r.latency_ms == 250.0


def test_sync_result_latency_ms_none_when_incomplete():
    r = LOSSyncResult(
        status=LOSSyncStatus.PENDING,
        direction=LOSSyncDirection.PUSH,
        loan_id=1,
    )
    assert r.latency_ms is None


# ---------------------------------------------------------------------------
# ConflictDetector — no-difference case
# ---------------------------------------------------------------------------

def test_conflict_detector_no_difference():
    det = ConflictDetector(strategy="crm_wins")
    out = det.detect_and_resolve(
        "rate", "6.50", "6.50", None, None, None,
    )
    assert out["is_conflict"] is False
    assert out["resolution"] == "no_change"


def test_conflict_detector_only_los_changed_no_conflict():
    det = ConflictDetector()
    last_sync = datetime(2026, 5, 1, tzinfo=timezone.utc)
    crm_modified = datetime(2026, 4, 1, tzinfo=timezone.utc)  # before last sync
    los_modified = datetime(2026, 5, 10, tzinfo=timezone.utc)
    out = det.detect_and_resolve(
        "rate", "6.5", "6.75", crm_modified, los_modified, last_sync,
    )
    assert out["is_conflict"] is False
    assert out["winning_side"] == "los"


def test_conflict_detector_true_conflict_crm_wins_strategy():
    det = ConflictDetector(strategy="crm_wins")
    last_sync = datetime(2026, 5, 1, tzinfo=timezone.utc)
    crm_mod = datetime(2026, 5, 5, tzinfo=timezone.utc)
    los_mod = datetime(2026, 5, 6, tzinfo=timezone.utc)
    out = det.detect_and_resolve(
        "rate", "6.5", "6.75", crm_mod, los_mod, last_sync,
    )
    assert out["is_conflict"] is True
    assert out["winning_value"] == "6.5"
    assert out["winning_side"] == "crm"


def test_conflict_detector_true_conflict_los_wins_strategy():
    det = ConflictDetector(strategy="los_wins")
    last_sync = datetime(2026, 5, 1, tzinfo=timezone.utc)
    crm_mod = datetime(2026, 5, 5, tzinfo=timezone.utc)
    los_mod = datetime(2026, 5, 6, tzinfo=timezone.utc)
    out = det.detect_and_resolve(
        "rate", "6.5", "6.75", crm_mod, los_mod, last_sync,
    )
    assert out["is_conflict"] is True
    assert out["winning_value"] == "6.75"
    assert out["winning_side"] == "los"


def test_conflict_detector_newest_wins_los_more_recent():
    det = ConflictDetector(strategy="newest_wins")
    last_sync = datetime(2026, 5, 1, tzinfo=timezone.utc)
    crm_mod = datetime(2026, 5, 5, tzinfo=timezone.utc)
    los_mod = datetime(2026, 5, 6, tzinfo=timezone.utc)  # later
    out = det.detect_and_resolve(
        "rate", "6.5", "6.75", crm_mod, los_mod, last_sync,
    )
    assert out["winning_side"] == "los"


def test_conflict_detector_manual_strategy_no_apply():
    det = ConflictDetector(strategy="manual")
    last_sync = datetime(2026, 5, 1, tzinfo=timezone.utc)
    crm_mod = datetime(2026, 5, 5, tzinfo=timezone.utc)
    los_mod = datetime(2026, 5, 6, tzinfo=timezone.utc)
    out = det.detect_and_resolve(
        "rate", "6.5", "6.75", crm_mod, los_mod, last_sync,
    )
    assert out["is_conflict"] is True
    assert out["winning_value"] is None
    assert out["winning_side"] == "manual"
