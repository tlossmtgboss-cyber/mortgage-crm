"""
Integration tests for backend/utils/lead_scoring.py.

Validates the calculate_lead_score algorithm produces deterministic scores
across weight bands (credit score, preapproval, contact info, DTI) and
clamps to the [0, 100] range.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


_scoring = _load("_pa_lead_scoring", "utils/lead_scoring.py")


@dataclass
class _StubLead:
    credit_score: Optional[int] = None
    preapproval_amount: Optional[float] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    debt_to_income: Optional[float] = None


# ---------------------------------------------------------------------------
# Baseline & determinism
# ---------------------------------------------------------------------------

def test_score_empty_lead_returns_baseline():
    # No data -> baseline 50
    assert _scoring.calculate_lead_score(_StubLead()) == 50


def test_score_is_deterministic():
    lead = _StubLead(credit_score=720, preapproval_amount=300000, email="a@b.com")
    s1 = _scoring.calculate_lead_score(lead)
    s2 = _scoring.calculate_lead_score(lead)
    assert s1 == s2


# ---------------------------------------------------------------------------
# Credit score bands
# ---------------------------------------------------------------------------

def test_score_excellent_credit_adds_30():
    assert _scoring.calculate_lead_score(_StubLead(credit_score=740)) == 80
    assert _scoring.calculate_lead_score(_StubLead(credit_score=800)) == 80


def test_score_good_credit_adds_20():
    assert _scoring.calculate_lead_score(_StubLead(credit_score=700)) == 70


def test_score_fair_credit_adds_10():
    assert _scoring.calculate_lead_score(_StubLead(credit_score=650)) == 60


def test_score_poor_credit_subtracts_10():
    assert _scoring.calculate_lead_score(_StubLead(credit_score=580)) == 40


# ---------------------------------------------------------------------------
# Preapproval boost
# ---------------------------------------------------------------------------

def test_score_with_preapproval_adds_15():
    assert _scoring.calculate_lead_score(_StubLead(preapproval_amount=250000)) == 65


def test_score_zero_preapproval_no_boost():
    assert _scoring.calculate_lead_score(_StubLead(preapproval_amount=0)) == 50


# ---------------------------------------------------------------------------
# Contact info boosts
# ---------------------------------------------------------------------------

def test_score_email_adds_5():
    assert _scoring.calculate_lead_score(_StubLead(email="x@y.com")) == 55


def test_score_phone_adds_5():
    assert _scoring.calculate_lead_score(_StubLead(phone="+15551234567")) == 55


def test_score_email_and_phone_add_10():
    assert _scoring.calculate_lead_score(_StubLead(email="x@y.com", phone="123")) == 60


# ---------------------------------------------------------------------------
# DTI bands
# ---------------------------------------------------------------------------

def test_score_low_dti_adds_10():
    assert _scoring.calculate_lead_score(_StubLead(debt_to_income=0.25)) == 60


def test_score_high_dti_subtracts_15():
    assert _scoring.calculate_lead_score(_StubLead(debt_to_income=0.60)) == 35


def test_score_midrange_dti_no_change():
    # 0.36 <= dti <= 0.50 -> no adjustment
    assert _scoring.calculate_lead_score(_StubLead(debt_to_income=0.45)) == 50


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------

def test_score_clamped_to_max_100():
    lead = _StubLead(
        credit_score=820,
        preapproval_amount=500000,
        email="a@b.com",
        phone="555",
        debt_to_income=0.20,
    )
    # 50 + 30 + 15 + 5 + 5 + 10 = 115 -> clamped to 100
    assert _scoring.calculate_lead_score(lead) == 100
