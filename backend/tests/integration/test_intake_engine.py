"""
Integration tests for backend/intake_engine/runtime models, validation,
and field normalization.

Covers PartyType, SessionStatus, FlagSeverity enums; ValidationEngine
regex patterns (email, phone, SSN, zip, currency); validation result
construction; party data classes.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


try:
    from intake_engine.runtime import models as _models  # type: ignore
    from intake_engine.runtime import validation as _validation  # type: ignore
except Exception as e:
    pytest.skip(f"intake_engine package not importable: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# PartyType + SessionStatus enums
# ---------------------------------------------------------------------------

def test_party_type_primary_value():
    assert _models.PartyType.PRIMARY == "PRIMARY"


def test_party_type_co_borrower():
    assert _models.PartyType.CO_BORROWER.value == "CO_BORROWER"


def test_session_status_active():
    assert _models.SessionStatus.ACTIVE == "ACTIVE"
    assert _models.SessionStatus.COMPLETE.value == "COMPLETE"


def test_flag_severity_ordering_exists():
    # All severity bands present
    levels = {s.value for s in _models.FlagSeverity}
    assert {"info", "warn", "high", "critical"}.issubset(levels)


def test_truth_band_has_5_bands():
    bands = {b.value for b in _models.TruthBand}
    assert bands == {"RED", "ORANGE", "YELLOW", "LIGHT_GREEN", "GREEN"}


def test_hesitation_band_includes_high():
    bands = {b.value for b in _models.HesitationBand}
    assert "high" in bands
    assert "none" in bands


# ---------------------------------------------------------------------------
# Party model defaults
# ---------------------------------------------------------------------------

def test_party_default_id_generated():
    p = _models.Party(party_type=_models.PartyType.PRIMARY)
    assert p.party_id.startswith("P_")
    assert p.is_complete is False


def test_party_two_parties_have_unique_ids():
    p1 = _models.Party(party_type=_models.PartyType.PRIMARY)
    p2 = _models.Party(party_type=_models.PartyType.CO_BORROWER)
    assert p1.party_id != p2.party_id


# ---------------------------------------------------------------------------
# Validation regex patterns
# ---------------------------------------------------------------------------

def test_email_pattern_matches_canonical():
    pat = _validation.ValidationEngine.PATTERNS["email"]
    assert re.match(pat, "user@example.com")


def test_email_pattern_rejects_no_at():
    pat = _validation.ValidationEngine.PATTERNS["email"]
    assert not re.match(pat, "no-at-sign")


def test_phone_pattern_matches_us_dashes():
    pat = _validation.ValidationEngine.PATTERNS["phone"]
    assert re.match(pat, "555-123-4567")


def test_phone_pattern_matches_parens():
    pat = _validation.ValidationEngine.PATTERNS["phone"]
    assert re.match(pat, "(555) 123-4567")


def test_ssn_pattern_matches_dashed_and_plain():
    pat = _validation.ValidationEngine.PATTERNS["ssn"]
    assert re.match(pat, "123-45-6789")
    assert re.match(pat, "123456789")


def test_zip_pattern_5_or_9_digits():
    pat = _validation.ValidationEngine.PATTERNS["zip"]
    assert re.match(pat, "94016")
    assert re.match(pat, "94016-1234")
    assert not re.match(pat, "9401")


def test_currency_pattern_with_dollar():
    pat = _validation.ValidationEngine.PATTERNS["currency"]
    assert re.match(pat, "$250,000.00")
    assert re.match(pat, "1000")


# ---------------------------------------------------------------------------
# ValidationResult construction
# ---------------------------------------------------------------------------

def test_validation_result_default_no_errors():
    vr = _validation.ValidationResult(valid=True)
    assert vr.valid is True
    assert vr.errors == []
    assert vr.warnings == []


def test_validation_result_with_errors():
    vr = _validation.ValidationResult(
        valid=False,
        errors=[{"code": "REQUIRED", "message": "x"}],
    )
    assert vr.valid is False
    assert len(vr.errors) == 1


# ---------------------------------------------------------------------------
# Additional enum coverage
# ---------------------------------------------------------------------------

def test_flag_category_truth_value():
    assert _models.FlagCategory.TRUTH == "truth"


def test_flag_category_compliance_value():
    assert _models.FlagCategory.COMPLIANCE == "compliance"


def test_data_class_restricted():
    assert _models.DataClass.RESTRICTED == "RESTRICTED"


def test_event_type_session_started():
    assert _models.EventType.SESSION_STARTED == "SESSION_STARTED"


def test_event_type_consent_captured():
    assert _models.EventType.CONSENT_CAPTURED == "CONSENT_CAPTURED"


def test_party_with_display_name():
    p = _models.Party(party_type=_models.PartyType.CO_BORROWER,
                       display_name="Jane Doe")
    assert p.display_name == "Jane Doe"
    assert p.party_type == _models.PartyType.CO_BORROWER


def test_ssn_last4_pattern_matches():
    pat = _validation.ValidationEngine.PATTERNS["ssn_last4"]
    assert re.match(pat, "1234")
    assert not re.match(pat, "123")
    assert not re.match(pat, "12345")
