"""
Extended integration tests for `agents/orchestration/compliance_guard.py`.

Covers TRID, ECOA prohibited-basis (per-class), RESPA, FDCPA, and APR-without-
disclosure / "guaranteed approval" / "best rate" rules.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_guard():
    target = _BACKEND_DIR / "agents" / "orchestration" / "compliance_guard.py"
    if not target.exists():
        pytest.skip("compliance_guard.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_compliance_guard_ext", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_cg = _load_guard()
guard = _cg.ComplianceGuard()


def _check(text):
    return guard.validate_response(text, agent_role="lead_nurturer")


def _has_rule(result, rule):
    return any(v.get("rule") == rule for v in result["violations"])


# ---------------------------------------------------------------------------
# TRID — guaranteed approval / promise of terms
# ---------------------------------------------------------------------------

def test_trid_guaranteed_approval_hard_blocks():
    r = _check("We guarantee approval on your loan today.")
    assert r["passed"] is False
    assert r["escalation_required"] is True


def test_trid_apr_without_disclosure_hard_blocks():
    r = _check("Your rate is 6.5% APR for this loan.")
    assert r["passed"] is False
    assert _has_rule(r, "apr_without_disclosure")


# ---------------------------------------------------------------------------
# ECOA prohibited basis (one per class)
# ---------------------------------------------------------------------------

def test_ecoa_race_prohibited_basis_blocks():
    r = _check("Because you are Hispanic we cannot approve this loan.")
    assert r["passed"] is False


def test_ecoa_age_prohibited_basis_blocks():
    r = _check("Because you are elderly we cannot proceed.")
    assert r["passed"] is False


def test_ecoa_sex_prohibited_basis_blocks():
    r = _check("Because you are female we will not approve.")
    assert r["passed"] is False


def test_ecoa_marital_status_prohibited_basis_blocks():
    r = _check("Because you are divorced we cannot approve.")
    assert r["passed"] is False


def test_ecoa_religion_prohibited_basis_blocks():
    r = _check("Because you are Muslim we cannot proceed.")
    assert r["passed"] is False


# ---------------------------------------------------------------------------
# RESPA — kickback language
# ---------------------------------------------------------------------------

def test_respa_kickback_language_blocks():
    r = _check("I'll pay you to refer clients to us.")
    assert r["passed"] is False


# ---------------------------------------------------------------------------
# FDCPA — threats
# ---------------------------------------------------------------------------

def test_fdcpa_threat_to_sue_blocks():
    r = _check("We will sue you if you don't pay.")
    assert r["passed"] is False


# ---------------------------------------------------------------------------
# Soft warn — "best rate" without disclaimer
# ---------------------------------------------------------------------------

def test_best_rate_without_disclaimer_warns_but_passes():
    r = _check("We offer the best rate in town.")
    # Soft-warn: passes but logs violation
    assert r["passed"] is True
    assert _has_rule(r, "best_rate_no_disclaimer")


# ---------------------------------------------------------------------------
# Best rate WITH disclaimer is neutralized
# ---------------------------------------------------------------------------

def test_best_rate_with_disclaimer_neutralized():
    r = _check(
        "We offer the best rate based on today's market. Individual rates may differ."
    )
    assert not _has_rule(r, "best_rate_no_disclaimer")


# ---------------------------------------------------------------------------
# Combination — multiple violations stacked
# ---------------------------------------------------------------------------

def test_combination_multiple_violations_recorded():
    r = _check(
        "We guarantee approval at an APR of 6.5% — definitely approved."
    )
    assert r["passed"] is False
    rules = {v["rule"] for v in r["violations"]}
    assert "guaranteed_approval" in rules
    assert "apr_without_disclosure" in rules
