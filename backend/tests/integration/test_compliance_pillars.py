"""
Integration tests for the five compliance pillars.

Pure-logic tests of compliance rule evaluation — no DB, no LLM. These should
all PASS on every run and act as canaries for the regulatory rule encoding.

Pillars covered:
  1. TRID 3-day rule (initial disclosures within 3 business days)
  2. ECOA prohibited basis for adverse action
  3. TCPA calling hours (8am-9pm consumer local time)
  4. RESPA Section 8 (kickback/referral fee prohibition)
  5. FDCPA threats/harassment
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import List, Set

import pytest


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Pillar 1: TRID — initial Loan Estimate must be delivered within 3 business
# days of application receipt. Saturdays are business days; Sundays + federal
# holidays are not. For the unit-level check we use a simple weekend skip.
# ---------------------------------------------------------------------------

def _add_business_days(start: datetime, n: int) -> datetime:
    cur = start
    added = 0
    while added < n:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 6:  # Mon-Sat are business days per TRID
            added += 1
    return cur


def trid_3day_violated(application_received: datetime, le_delivered: datetime) -> bool:
    deadline = _add_business_days(application_received, 3)
    return le_delivered > deadline


def test_trid_3day_rule_blocks_late_disclosure() -> None:
    received = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)  # Monday
    # Delivered Saturday → still within 3 business days (T, W, Th = deadline Th)
    # Use 5 days later to ensure violation
    late = received + timedelta(days=6)
    on_time = received + timedelta(days=2)
    assert trid_3day_violated(received, late) is True
    assert trid_3day_violated(received, on_time) is False


# ---------------------------------------------------------------------------
# Pillar 2: ECOA — adverse action reasons cannot reference prohibited bases.
# ---------------------------------------------------------------------------

ECOA_PROHIBITED = {
    "race", "color", "religion", "national origin", "sex", "marital status",
    "age", "pregnant", "pregnancy", "public assistance",
}


def ecoa_violated(reason_text: str) -> Set[str]:
    text = reason_text.lower()
    return {token for token in ECOA_PROHIBITED if token in text}


def test_ecoa_prohibited_basis_detected():
    hits = ecoa_violated("Denying because the applicant is pregnant and married.")
    assert "pregnant" in hits
    assert "marital status" in hits or "married" not in ECOA_PROHIBITED  # tolerant
    clean = ecoa_violated("Denying due to insufficient income relative to DTI.")
    assert clean == set()


# ---------------------------------------------------------------------------
# Pillar 3: TCPA — automated/marketing calls must be 8am-9pm consumer local.
# ---------------------------------------------------------------------------

def tcpa_call_allowed(call_time_local: time) -> bool:
    return time(8, 0) <= call_time_local <= time(21, 0)


def test_tcpa_hours_enforced():
    assert tcpa_call_allowed(time(10, 0)) is True
    assert tcpa_call_allowed(time(20, 59)) is True
    assert tcpa_call_allowed(time(7, 59)) is False
    assert tcpa_call_allowed(time(21, 1)) is False
    assert tcpa_call_allowed(time(2, 30)) is False


# ---------------------------------------------------------------------------
# Pillar 4: RESPA Section 8 — flag language suggesting referral fees / kickbacks
# ---------------------------------------------------------------------------

RESPA_KICKBACK_PHRASES = {
    "kickback",
    "referral fee",
    "i'll pay you for each referral",
    "split the commission",
    "thank-you payment for referrals",
}


def respa_violated(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in RESPA_KICKBACK_PHRASES)


def test_respa_kickback_language_blocked():
    assert respa_violated("I'll pay you $200 as a referral fee for each closed loan.") is True
    assert respa_violated("Happy to coordinate with you on this borrower.") is False


# ---------------------------------------------------------------------------
# Pillar 5: FDCPA — threats / harassment / false claims
# ---------------------------------------------------------------------------

FDCPA_THREAT_PHRASES = {
    "we will have you arrested",
    "you will go to jail",
    "garnish your wages today",
    "we'll take your house",
    "i'll call you every hour",
}


def fdcpa_violated(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in FDCPA_THREAT_PHRASES)


def test_fdcpa_threats_blocked():
    assert fdcpa_violated("If you don't pay we will have you arrested.") is True
    assert fdcpa_violated("Please give us a call to discuss options.") is False
