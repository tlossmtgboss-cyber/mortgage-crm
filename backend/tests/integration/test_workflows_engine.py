"""
Integration tests for backend/workflows/*.py engines.

Covers the pure-logic surface of:
  - lead_workflow_engine: VALID_TRANSITIONS, TIME_RULES, LEAD_STAGES
  - document_intake_engine: LOAN_NUMBER_PATTERNS, DOC_TYPE_FILENAME_PATTERNS,
    file-size constants
  - rate_lock_engine: RateLockIntelligenceEngine eligibility + scoring +
    recommendation helpers
  - post_closing_workflow: HIGH/MEDIUM thresholds, industry list,
    LeadWorkflowData defaults

The full engines are DB-backed; these tests target the side-effect-free
classifiers and constants that don't require a Session.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str, stubs: dict | None = None):
    if stubs:
        for sname, smod in stubs.items():
            sys.modules.setdefault(sname, smod)
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Lead Workflow Engine
# ---------------------------------------------------------------------------

_lwe = _load("_pa_lead_wf", "workflows/lead_workflow_engine.py")


def test_lead_stages_contains_15_stages():
    assert "New" in _lwe.LEAD_STAGES
    assert "Pre-Approved" in _lwe.LEAD_STAGES
    assert "Closed" in _lwe.LEAD_STAGES
    assert len(_lwe.LEAD_STAGES) == 15


def test_lead_initial_transition_only_to_new():
    assert _lwe.VALID_TRANSITIONS[None] == ["New"]


def test_lead_new_can_transition_to_attempted_contact():
    assert "Attempted Contact" in _lwe.VALID_TRANSITIONS["New"]


def test_lead_terminal_does_not_qualify_in_target_set():
    # Multiple states should be able to land in Does Not Qualify
    sources_to_dnq = [
        s for s, targets in _lwe.VALID_TRANSITIONS.items()
        if targets and "Does Not Qualify" in targets
    ]
    assert len(sources_to_dnq) >= 4


def test_lead_invalid_transition_new_to_closed():
    # Cannot jump from New straight to Closed
    assert "Closed" not in _lwe.VALID_TRANSITIONS["New"]


def test_lead_time_rules_escalation_is_after_no_contact():
    assert _lwe.TIME_RULES["new_escalate"] > _lwe.TIME_RULES["new_no_contact"]


def test_lead_time_rules_all_positive_hours():
    for k, v in _lwe.TIME_RULES.items():
        assert v > 0, f"{k} must be positive"


def test_lead_workflow_action_schema_minimal():
    action = _lwe.WorkflowAction(action_type="email", target="lead")
    assert action.action_type == "email"
    assert action.priority == "normal"


# ---------------------------------------------------------------------------
# Document Intake Engine
# ---------------------------------------------------------------------------

# Stub the s3 service before loading
from types import ModuleType
import unittest.mock as _mock

_s3_stub = ModuleType("services.perennia_s3_service")
_s3_stub.get_s3_service = lambda: _mock.MagicMock()
_services_stub = ModuleType("services")
_services_stub.__path__ = []
sys.modules.setdefault("services", _services_stub)
sys.modules["services.perennia_s3_service"] = _s3_stub

_die = _load("_pa_doc_intake", "workflows/document_intake_engine.py")


def test_doc_intake_loan_number_pattern_matches_basic():
    # "Loan #: 1234567" should match
    for pat in _die.LOAN_NUMBER_PATTERNS:
        if re.search(pat, "Loan #: 1234567", re.IGNORECASE):
            return
    pytest.fail("No loan number pattern matched standard format")


def test_doc_intake_classifies_w2_filename():
    patterns = _die.DOC_TYPE_FILENAME_PATTERNS["W2"]
    assert any(re.search(p, "borrower_w2_2024.pdf", re.IGNORECASE) for p in patterns)


def test_doc_intake_classifies_paystub_filename():
    patterns = _die.DOC_TYPE_FILENAME_PATTERNS["PAYSTUB"]
    assert any(re.search(p, "Recent_Paystub.pdf", re.IGNORECASE) for p in patterns)


def test_doc_intake_min_filesize_filters_small_files():
    assert _die.MIN_FILE_SIZE_BYTES >= 1000
    assert _die.MAX_FILE_SIZE_BYTES > _die.MIN_FILE_SIZE_BYTES


def test_doc_intake_valid_attachment_types_includes_pdf():
    assert "application/pdf" in _die.VALID_ATTACHMENT_TYPES
    assert ".pdf" in _die.VALID_ATTACHMENT_TYPES["application/pdf"]


# ---------------------------------------------------------------------------
# Rate Lock Engine
# ---------------------------------------------------------------------------

_rle = _load("_pa_rate_lock", "workflows/rate_lock_engine.py")


def _make_loan(closing_in_days=20, property_id=True, structure_done=True,
               lock_status="Floating"):
    return _rle.LoanContext(
        loan_id=1, loan_number="L1", borrower_name="X",
        loan_amount=300000, current_rate=6.5,
        closing_date=datetime.now(timezone.utc) + timedelta(days=closing_in_days),
        lock_date=None, lock_expiration_date=None, lock_term_days=None,
        rate_lock_status=lock_status,
        borrower_risk_profile=None,
        property_identified=property_id,
        loan_structure_complete=structure_done,
    )


def _make_market(mbs_change=0.0, vol=30, treasury10=4.2):
    return _rle.MarketSnapshot(
        treasury_10yr=treasury10, treasury_2yr=4.5,
        mortgage_30yr=6.75, mbs_price=100.5,
        mbs_change=mbs_change, volatility_score=vol,
        timestamp=datetime.now(timezone.utc),
    )


def test_rate_lock_eligibility_complete_returns_true():
    eng = _rle.RateLockIntelligenceEngine()
    ok, msg = eng.check_eligibility(_make_loan())
    assert ok is True
    assert "Eligible" in msg


def test_rate_lock_eligibility_no_property_returns_false():
    eng = _rle.RateLockIntelligenceEngine()
    ok, msg = eng.check_eligibility(_make_loan(property_id=False))
    assert ok is False
    assert "property" in msg.lower()


def test_rate_lock_risk_level_critical_under_7_days():
    eng = _rle.RateLockIntelligenceEngine()
    level, mod = eng.get_risk_level(5)
    assert level == "CRITICAL"
    assert mod > 0


def test_rate_lock_risk_level_minimal_far_out():
    eng = _rle.RateLockIntelligenceEngine()
    level, mod = eng.get_risk_level(60)
    assert level == "MINIMAL"


def test_rate_lock_score_in_bounds_for_neutral_market():
    eng = _rle.RateLockIntelligenceEngine()
    score = eng.calculate_lock_score(_make_market(), _make_loan(), 20)
    assert 0 <= score <= 100


def test_rate_lock_score_drops_on_mbs_collapse():
    eng = _rle.RateLockIntelligenceEngine()
    bull = eng.calculate_lock_score(_make_market(mbs_change=30), _make_loan(), 20)
    bear = eng.calculate_lock_score(_make_market(mbs_change=-30), _make_loan(), 20)
    assert bull > bear


# ---------------------------------------------------------------------------
# Post-Closing Workflow
# ---------------------------------------------------------------------------

_pcw = _load("_pa_post_close", "workflows/post_closing_workflow.py")


def test_post_closing_high_threshold_is_80():
    assert _pcw.HIGH_REFERRAL_SCORE == 80


def test_post_closing_medium_threshold_is_50():
    assert _pcw.MEDIUM_REFERRAL_SCORE == 50


def test_post_closing_industries_include_real_estate():
    assert "Real Estate" in _pcw.HIGH_REFERRAL_INDUSTRIES
    assert "Healthcare" in _pcw.HIGH_REFERRAL_INDUSTRIES


def test_post_closing_lead_data_defaults():
    lead = _pcw.LeadWorkflowData(id=1, name="John Doe")
    assert lead.first_name == "John"
    assert lead.referral_source_score == 0
    assert lead.employees_managed == 0
