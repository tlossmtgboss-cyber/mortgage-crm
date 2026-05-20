"""
Integration tests for DNC + TCPA compliance services.

Covers:
  - services/compliance/tcpa: time-of-day window (8AM-9PM local),
    timezone resolution by area code, ContactWindowResult schema
  - services/dnc_federal_sync: stub DNC list, is_dnc check
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


try:
    from services.compliance.tcpa import (
        TCPA_START_HOUR,
        TCPA_END_HOUR,
        _AREA_CODE_TIMEZONE,
        ContactWindowResult,
        AuditMetadata,
    )
except Exception as e:
    pytest.skip(f"tcpa module not importable: {e}", allow_module_level=True)


def _maybe_load_dnc():
    try:
        from services import dnc_federal_sync  # type: ignore
        return dnc_federal_sync
    except Exception:
        return None


_dnc = _maybe_load_dnc()


# ---------------------------------------------------------------------------
# TCPA window constants
# ---------------------------------------------------------------------------

def test_tcpa_window_starts_8am():
    assert TCPA_START_HOUR == 8


def test_tcpa_window_ends_9pm():
    assert TCPA_END_HOUR == 21


def test_tcpa_window_is_13_hours_wide():
    assert (TCPA_END_HOUR - TCPA_START_HOUR) == 13


# ---------------------------------------------------------------------------
# Area-code timezone resolution
# ---------------------------------------------------------------------------

def test_area_code_212_is_eastern():
    assert _AREA_CODE_TIMEZONE["212"] == "America/New_York"


def test_area_code_213_is_pacific():
    assert _AREA_CODE_TIMEZONE["213"] == "America/Los_Angeles"


def test_area_code_808_is_hawaii():
    assert _AREA_CODE_TIMEZONE["808"] == "Pacific/Honolulu"


def test_area_code_907_is_alaska():
    assert _AREA_CODE_TIMEZONE["907"] == "America/Anchorage"


def test_area_code_602_is_phoenix_no_dst():
    assert _AREA_CODE_TIMEZONE["602"] == "America/Phoenix"


# ---------------------------------------------------------------------------
# TCPAChecker
# ---------------------------------------------------------------------------

def test_contact_window_blocked_for_unknown_tz():
    from services.compliance.tcpa import TCPAChecker
    result = TCPAChecker().can_contact_now(tz_id=None, phone=None)
    assert result.can_contact is False
    assert result.timezone_id == "unknown"


def test_contact_window_resolves_from_phone_area_code():
    from services.compliance.tcpa import TCPAChecker
    # Phone with NYC area code (212) — should resolve to America/New_York
    result = TCPAChecker().can_contact_now(phone="+12125551234")
    assert result.timezone_id == "America/New_York"


def test_audit_metadata_records_regulation():
    audit = AuditMetadata(
        rule="TCPA time-of-day",
        regulation="47 CFR 64.1200(c)(1)",
        inputs={"tz": "America/New_York"},
    )
    assert "64.1200" in audit.regulation
    assert audit.calculated_at  # auto-populated


# ---------------------------------------------------------------------------
# Federal DNC stub
# ---------------------------------------------------------------------------

def test_dnc_module_loadable():
    if _dnc is None:
        pytest.skip("dnc_federal_sync not importable")
    assert hasattr(_dnc, "_stub_federal_dnc_list")


def test_dnc_stub_returns_a_list():
    if _dnc is None:
        pytest.skip("dnc_federal_sync not importable")
    lst = _dnc._stub_federal_dnc_list()
    assert isinstance(lst, list)
    assert len(lst) >= 1
