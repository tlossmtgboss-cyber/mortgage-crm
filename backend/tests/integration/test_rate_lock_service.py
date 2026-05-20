"""
Integration tests for the rate lock engine — extension strategy,
float-down opportunity detection, recommendations, and full analysis.

The DB-bound rate_lock_monitor lives in services/ and requires a Session;
this test targets the pure-logic methods on RateLockIntelligenceEngine.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_rle = _load("_pa_rate_lock_svc", "workflows/rate_lock_engine.py")


def _market(mbs_change=0.0, vol=30, mortgage_30yr=6.75):
    return _rle.MarketSnapshot(
        treasury_10yr=4.2, treasury_2yr=4.5,
        mortgage_30yr=mortgage_30yr, mbs_price=100.5,
        mbs_change=mbs_change, volatility_score=vol,
        timestamp=datetime.now(timezone.utc),
    )


def _loan(closing_in=20, lock_status="Floating", loan_amount=300000,
          lock_expires_in=None):
    lock_exp = None
    if lock_expires_in is not None:
        lock_exp = datetime.now(timezone.utc) + timedelta(days=lock_expires_in)
    return _rle.LoanContext(
        loan_id=1, loan_number="L1", borrower_name="X",
        loan_amount=loan_amount, current_rate=6.5,
        closing_date=datetime.now(timezone.utc) + timedelta(days=closing_in),
        lock_date=None, lock_expiration_date=lock_exp, lock_term_days=None,
        rate_lock_status=lock_status,
        borrower_risk_profile=None,
        property_identified=True, loan_structure_complete=True,
    )


# ---------------------------------------------------------------------------
# Eligibility — additional cases
# ---------------------------------------------------------------------------

def test_eligibility_missing_closing_date_rejects():
    loan = _loan()
    loan.closing_date = None
    ok, msg = _rle.RateLockIntelligenceEngine().check_eligibility(loan)
    assert ok is False
    assert "closing" in msg.lower()


def test_eligibility_incomplete_structure_rejects():
    loan = _loan()
    loan.loan_structure_complete = False
    ok, _ = _rle.RateLockIntelligenceEngine().check_eligibility(loan)
    assert ok is False


# ---------------------------------------------------------------------------
# days_to_close and risk_level
# ---------------------------------------------------------------------------

def test_days_to_close_none_for_missing_date():
    eng = _rle.RateLockIntelligenceEngine()
    assert eng.calculate_days_to_close(None) is None


def test_risk_level_unknown_for_none():
    eng = _rle.RateLockIntelligenceEngine()
    level, mod = eng.get_risk_level(None)
    assert level == "UNKNOWN"
    assert mod == 0


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

def test_recommendation_strong_score_locks_now():
    eng = _rle.RateLockIntelligenceEngine()
    rec, _ = eng.get_recommendation(80, 20, _loan())
    assert rec == "LOCK_NOW"


def test_recommendation_lock_about_to_expire_extends():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Locked", lock_expires_in=3)
    rec, _ = eng.get_recommendation(60, 15, loan)
    assert rec == "EXTEND_LOCK"


def test_recommendation_expired_lock_relocks():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Lock Expired")
    rec, _ = eng.get_recommendation(50, 20, loan)
    assert rec == "RELOCK"


# ---------------------------------------------------------------------------
# Float-down opportunity
# ---------------------------------------------------------------------------

def test_float_down_unavailable_when_floating():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Floating")
    out = eng.check_float_down_opportunity(loan, _market(), original_rate=7.0)
    assert out["available"] is False


def test_float_down_unavailable_when_no_improvement():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Locked", loan_amount=300000)
    # Locked at 6.75; market also at 6.75 -> 0% improvement
    out = eng.check_float_down_opportunity(loan, _market(mortgage_30yr=6.75),
                                            original_rate=6.75)
    assert out["available"] is False


def test_float_down_available_with_improvement():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Locked", loan_amount=400000)
    # Locked at 7.5; market at 6.75 -> 0.75% improvement
    out = eng.check_float_down_opportunity(loan, _market(mortgage_30yr=6.75),
                                            original_rate=7.5)
    assert out["available"] is True
    assert out["estimated_monthly_savings"] > 0


# ---------------------------------------------------------------------------
# Extension strategy
# ---------------------------------------------------------------------------

def test_extension_not_needed_when_not_locked():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Floating")
    out = eng.analyze_extension_strategy(loan)
    assert out["needed"] is False


def test_extension_recommended_when_5_days_out():
    eng = _rle.RateLockIntelligenceEngine()
    loan = _loan(lock_status="Locked", lock_expires_in=4, loan_amount=300000)
    out = eng.analyze_extension_strategy(loan, expected_delay_days=15)
    assert out["needed"] is True
    assert out["recommendation"] == "EXTEND_LOCK"
    assert out["extension_cost_dollars"] > 0
