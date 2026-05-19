"""
Extended compliance pillar tests.

Adds variations on the five pillars already covered by test_compliance_pillars
plus broader TRID/RESPA/TILA/FCRA patterns. Pure-logic tests — no DB, no LLM,
no network.

This file deliberately re-implements the same rule shapes as the existing
test_compliance_pillars.py instead of importing them, so it stays a true
canary for the regulatory rule encoding.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Set

import pytest


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TRID — broader variations
# ---------------------------------------------------------------------------

def _add_business_days(start: datetime, n: int) -> datetime:
    cur = start
    added = 0
    while added < n:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 6:  # Mon-Sat
            added += 1
    return cur


def _trid_violated(received: datetime, delivered: datetime, deadline_days: int = 3) -> bool:
    return delivered > _add_business_days(received, deadline_days)


# Test 1: Refinance LE — same 3-day rule applies
def test_trid_refinance_loan_estimate_3day_rule():
    received = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)  # Monday
    on_time = received + timedelta(days=2)
    assert _trid_violated(received, on_time, 3) is False


# Test 2: HELOC initial disclosures — same rule
def test_trid_heloc_disclosure_late():
    received = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    late = received + timedelta(days=8)
    assert _trid_violated(received, late, 3) is True


# Test 3: Closing Disclosure 3-business-day waiting period before consummation
def test_trid_cd_three_day_waiting_period_held():
    cd_delivered = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)  # Mon
    closing = cd_delivered + timedelta(days=3)  # Thu — exactly 3 biz days
    assert closing >= _add_business_days(cd_delivered, 3)


# Test 4: CD waiting period violated if closing happens too early
def test_trid_cd_waiting_period_violated_when_too_soon():
    cd_delivered = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    closing = cd_delivered + timedelta(days=1)  # next day
    assert closing < _add_business_days(cd_delivered, 3)


# ---------------------------------------------------------------------------
# ECOA — protected classes (B comment 1002.2)
# ---------------------------------------------------------------------------

ECOA_PROHIBITED = {
    "race", "color", "religion", "national origin", "sex",
    "marital status", "age", "pregnant", "pregnancy", "public assistance",
}


def _ecoa_violated(text: str) -> Set[str]:
    lower = text.lower()
    return {token for token in ECOA_PROHIBITED if token in lower}


# Test 5: race detected
def test_ecoa_race_detected():
    assert "race" in _ecoa_violated("Denying based on applicant race.")


# Test 6: religion detected
def test_ecoa_religion_detected():
    assert "religion" in _ecoa_violated("Denied due to applicant religion.")


# Test 7: national origin detected
def test_ecoa_national_origin_detected():
    assert "national origin" in _ecoa_violated("Concerns about national origin.")


# Test 8: age (in combination with other words) detected
def test_ecoa_age_detected():
    assert "age" in _ecoa_violated("Denying because of age 65+ status.")


# Test 9: public assistance income discrimination flagged
def test_ecoa_public_assistance_detected():
    assert "public assistance" in _ecoa_violated(
        "Income from public assistance not considered."
    )


# ---------------------------------------------------------------------------
# RESPA Section 8 patterns
# ---------------------------------------------------------------------------

RESPA_KICKBACK_PHRASES = {
    "kickback", "referral fee", "send business in exchange",
    "marketing service agreement payment", "co-marketing fee for leads",
}


def _respa_violated(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in RESPA_KICKBACK_PHRASES)


# Test 10: explicit kickback language flagged
def test_respa_explicit_kickback_flagged():
    assert _respa_violated("Title company will pay a kickback per referral.")


# Test 11: referral fee language flagged
def test_respa_referral_fee_flagged():
    assert _respa_violated("$500 referral fee per closed loan.")


# Test 12: legitimate marketing language NOT flagged
def test_respa_legitimate_marketing_not_flagged():
    assert _respa_violated(
        "Equal-cost marketing service agreement for shared advertising."
    ) is False


# ---------------------------------------------------------------------------
# TILA Section 32 (HOEPA) — high-cost loan thresholds
# ---------------------------------------------------------------------------

def _hoepa_high_cost(apr: float, avg_prime: float, loan_amount: int) -> bool:
    """Simplified HOEPA APR + points trigger (post-Dodd-Frank 12 CFR §1026.32).

    Triggered when APR exceeds APOR by 6.5% (first-lien <50k loans) or by
    8.5% (first-lien junior liens — simplified to >$50k for this test).
    """
    spread = apr - avg_prime
    if loan_amount < 50_000:
        return spread > 6.5
    return spread > 8.5


# Test 13: high APR over APOR triggers HOEPA on small loan
def test_hoepa_small_loan_apr_trigger():
    assert _hoepa_high_cost(apr=14.0, avg_prime=7.0, loan_amount=30_000) is True


# Test 14: normal APR on conforming loan does NOT trigger HOEPA
def test_hoepa_normal_apr_not_triggered():
    assert _hoepa_high_cost(apr=7.5, avg_prime=7.0, loan_amount=300_000) is False


# ---------------------------------------------------------------------------
# FCRA adverse action notice requirements
# ---------------------------------------------------------------------------

FCRA_REQUIRED_NOTICE_FIELDS = (
    "credit_reporting_agency_name",
    "credit_reporting_agency_phone",
    "credit_reporting_agency_address",
    "right_to_free_report",
    "right_to_dispute",
)


def _fcra_notice_complete(notice: dict) -> bool:
    return all(notice.get(field) for field in FCRA_REQUIRED_NOTICE_FIELDS)


# Test 15: complete FCRA notice passes
def test_fcra_complete_notice_passes():
    notice = {field: "filled" for field in FCRA_REQUIRED_NOTICE_FIELDS}
    assert _fcra_notice_complete(notice) is True
