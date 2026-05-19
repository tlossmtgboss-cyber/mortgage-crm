"""
Integration tests for the pre-response Compliance Guard.

Exercises the real `agents.orchestration.compliance_guard.ComplianceGuard`
scanner with no DB and no LLM — these tests are deterministic and fast and
should all PASS on every run. They are the canary that proves the
integration test harness itself collects and executes correctly.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _load_compliance_guard():
    """Load the compliance_guard module by file path so we don't trigger the
    heavy ``agents/__init__.py`` (which imports langgraph + the full agent
    fleet). This keeps the integration test surface small and fast.
    """
    backend_dir = Path(__file__).resolve().parents[2]
    target = backend_dir / "agents" / "orchestration" / "compliance_guard.py"
    if not target.exists():  # pragma: no cover - safety net
        pytest.skip(f"compliance_guard.py not found at {target}")
    spec = importlib.util.spec_from_file_location(
        "_perennia_compliance_guard_under_test", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_cg_module = _load_compliance_guard()
ComplianceGuard = _cg_module.ComplianceGuard
compliance_guard = _cg_module.compliance_guard


@pytest.fixture
def guard() -> ComplianceGuard:
    return compliance_guard


# ---------------------------------------------------------------------------
# 1. Guaranteed-approval language must HARD-BLOCK
# ---------------------------------------------------------------------------

def test_guaranteed_approval_is_hard_blocked(guard):
    res = guard.validate_response(
        "Good news — we guarantee approval on your loan today.",
        agent_role="lead_nurturer",
    )
    assert res["passed"] is False
    assert res["escalation_required"] is True
    rules = {v["rule"] for v in res["violations"]}
    assert "guaranteed_approval" in rules


# ---------------------------------------------------------------------------
# 2. ECOA-prohibited reasoning must HARD-BLOCK
# ---------------------------------------------------------------------------

def test_ecoa_prohibited_basis_is_hard_blocked(guard):
    res = guard.validate_response(
        "I'm denying this loan because you're married and pregnant.",
        agent_role="underwriter",
    )
    assert res["passed"] is False
    assert res["escalation_required"] is True
    regulations = {v["regulation"] for v in res["violations"]}
    assert "ECOA" in regulations


# ---------------------------------------------------------------------------
# 3. APR mentioned without TRID disclosure must HARD-BLOCK; with disclosure passes
# ---------------------------------------------------------------------------

def test_apr_without_disclosure_is_flagged(guard):
    # Without disclosure → block
    bad = guard.validate_response(
        "Your APR of 6.5% looks great.",
        agent_role="loan_officer",
    )
    assert bad["passed"] is False
    rules = {v["rule"] for v in bad["violations"]}
    assert "apr_without_disclosure" in rules

    # With disclosure → passes
    good = guard.validate_response(
        "Your APR of 6.5% looks great — subject to credit approval.",
        agent_role="loan_officer",
    )
    apr_rules = {v["rule"] for v in good["violations"]}
    assert "apr_without_disclosure" not in apr_rules


# ---------------------------------------------------------------------------
# 4. "Best rate" without comparative disclaimer is a SOFT WARN (not a block)
# ---------------------------------------------------------------------------

def test_best_rate_is_soft_warned_not_blocked(guard):
    res = guard.validate_response(
        "We offer the best rate around. Period.",
        agent_role="marketing_agent",
    )
    # Soft-warn rule should appear, but the message still passes overall.
    assert res["passed"] is True
    assert res["escalation_required"] is False
    rules = {v["rule"] for v in res["violations"]}
    assert "best_rate_no_disclaimer" in rules
    severities = {v["severity"] for v in res["violations"]}
    assert severities == {"warn"}

    # Adding a comparative disclaimer neutralizes the warning.
    res2 = guard.validate_response(
        "We offer the best rate among lenders we surveyed this week.",
        agent_role="marketing_agent",
    )
    rules2 = {v["rule"] for v in res2["violations"]}
    assert "best_rate_no_disclaimer" not in rules2


# ---------------------------------------------------------------------------
# 5. A compliant response passes through untouched
# ---------------------------------------------------------------------------

def test_compliant_response_passes_through(guard):
    res = guard.validate_response(
        "Thanks for reaching out — I'll review your application and follow up "
        "within one business day. Final terms are subject to credit approval.",
        agent_role="loan_officer",
    )
    assert res["passed"] is True
    assert res["escalation_required"] is False
    assert res["violations"] == []
