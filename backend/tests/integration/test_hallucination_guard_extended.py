"""
Extended integration tests for `agents/orchestration/hallucination_guard.py`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_guard():
    target = _BACKEND_DIR / "agents" / "orchestration" / "hallucination_guard.py"
    if not target.exists():
        pytest.skip("hallucination_guard.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_hallucination_guard_ext", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_hg = _load_guard()
guard = _hg.HallucinationGuard()


# ---------------------------------------------------------------------------
# 1. Currency claim verified against matching context
# ---------------------------------------------------------------------------

def test_currency_claim_verified_against_context():
    res = guard.verify_claims(
        "Loan amount: $250,000.",
        context_data={"loan_amount": "$250,000"},
    )
    assert res["verified"] is True
    assert res["confidence"] == 1.0


# ---------------------------------------------------------------------------
# 2. Date claim verified against matching context
# ---------------------------------------------------------------------------

def test_date_claim_verified_against_context():
    res = guard.verify_claims(
        "Closing on 2026-06-15.",
        context_data={"close_date": "2026-06-15"},
    )
    assert res["verified"] is True


# ---------------------------------------------------------------------------
# 3. Percentage claim verified against matching context
# ---------------------------------------------------------------------------

def test_percent_claim_verified_against_context():
    res = guard.verify_claims(
        "Rate is 6.5%.",
        context_data={"rate": "6.5%"},
    )
    assert res["verified"] is True


# ---------------------------------------------------------------------------
# 4. Nested context walking — value buried inside list/dict
# ---------------------------------------------------------------------------

def test_nested_context_walked_recursively():
    res = guard.verify_claims(
        "Closing on 2026-06-15.",
        context_data={"loan": {"milestones": [{"name": "close", "date": "2026-06-15"}]}},
    )
    assert res["verified"] is True


# ---------------------------------------------------------------------------
# 5. Missing context → unverified, but confidence is computable
# ---------------------------------------------------------------------------

def test_missing_context_returns_unverified():
    res = guard.verify_claims("Rate is 6.5%.", context_data=None)
    assert res["verified"] is False
    assert "6.5%" in res["unverified_claims"]


# ---------------------------------------------------------------------------
# 6. Mismatched currency flagged
# ---------------------------------------------------------------------------

def test_mismatched_currency_flagged_as_unverified():
    res = guard.verify_claims(
        "Loan amount: $300,000.",
        context_data={"loan_amount": "$250,000"},
    )
    assert res["verified"] is False


# ---------------------------------------------------------------------------
# 7. Ambiguous date flagged (no overlap)
# ---------------------------------------------------------------------------

def test_ambiguous_date_flagged():
    res = guard.verify_claims(
        "Closing on May 19, 2026.",
        context_data={"close_date": "2027-01-01"},
    )
    assert res["verified"] is False


# ---------------------------------------------------------------------------
# 8. Confidence threshold — partial verification
# ---------------------------------------------------------------------------

def test_partial_verification_yields_intermediate_confidence():
    res = guard.verify_claims(
        "Rate is 6.5% and amount is $250,000.",
        context_data={"rate": "6.5%"},  # amount unverified
    )
    assert 0 < res["confidence"] < 1.0


# ---------------------------------------------------------------------------
# 9. Empty claims string → verified True / conf 1.0
# ---------------------------------------------------------------------------

def test_empty_text_returns_verified_true():
    res = guard.verify_claims("", context_data={"x": 1})
    assert res["verified"] is True
    assert res["confidence"] == 1.0


# ---------------------------------------------------------------------------
# 10. Recursive list walk — list of dicts
# ---------------------------------------------------------------------------

def test_list_of_dicts_walked():
    res = guard.verify_claims(
        "Amount $1,000.",
        context_data=[{"a": "$1,000"}, {"b": "other"}],
    )
    assert res["verified"] is True
