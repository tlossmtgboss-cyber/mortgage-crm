"""
D3 — Agent Fleet Governance Tests

Covers:
    * TokenBudgetManager  — budget enforcement, usage accounting, reset
    * ComplianceGuard     — hard-block + soft-warn detection (TRID/RESPA/ECOA/TCPA/FDCPA)
    * HallucinationGuard  — unverified numeric/date claim flagging
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Load the three guardrail modules directly by file path. This avoids
# importing `agents/__init__.py`, which pulls in langgraph and other
# runtime deps that aren't needed for these pure-logic tests.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCH_DIR = os.path.abspath(os.path.join(_HERE, "..", "agents", "orchestration"))


def _load(mod_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(_ORCH_DIR, filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_token_budget_mod = _load("token_budget_isolated", "token_budget.py")
_compliance_mod = _load("compliance_guard_isolated", "compliance_guard.py")
_hallucination_mod = _load("hallucination_guard_isolated", "hallucination_guard.py")

TokenBudgetManager = _token_budget_mod.TokenBudgetManager
ComplianceGuard = _compliance_mod.ComplianceGuard
compliance_guard = _compliance_mod.compliance_guard
HallucinationGuard = _hallucination_mod.HallucinationGuard
hallucination_guard = _hallucination_mod.hallucination_guard


# ---------- TokenBudgetManager -----------------------------------------

class TestTokenBudgetManager:
    def test_check_and_reserve_within_budget(self):
        mgr = TokenBudgetManager(default_budget_tokens=1000)
        assert mgr.check_and_reserve("agent-a", 500) is True

    def test_check_and_reserve_rejects_overage(self):
        mgr = TokenBudgetManager(default_budget_tokens=1000)
        mgr.record_usage("agent-a", 600, 300)  # 900 used
        # Request 200 more → 1100 projected, > 1000 budget → reject
        assert mgr.check_and_reserve("agent-a", 200) is False

    def test_record_usage_accumulates(self):
        mgr = TokenBudgetManager(default_budget_tokens=10_000)
        mgr.record_usage("agent-b", 100, 200)
        mgr.record_usage("agent-b", 50, 50)
        snap = mgr.get_usage("agent-b")
        assert snap["tokens_used"] == 400
        assert snap["tokens_remaining"] == 9_600
        assert snap["pct_utilization"] == pytest.approx(0.04)

    def test_per_agent_override(self):
        mgr = TokenBudgetManager(
            default_budget_tokens=1000,
            per_agent_overrides={"vip-agent": 5000},
        )
        assert mgr.check_and_reserve("vip-agent", 4500) is True
        assert mgr.check_and_reserve("vip-agent", 6000) is False

    def test_reset_daily_clears_usage(self):
        mgr = TokenBudgetManager(default_budget_tokens=1000)
        mgr.record_usage("agent-c", 500, 0)
        mgr.reset_daily()
        snap = mgr.get_usage("agent-c")
        assert snap["tokens_used"] == 0
        assert snap["tokens_remaining"] == 1000

    def test_warning_at_80_percent(self, caplog):
        import logging
        mgr = TokenBudgetManager(default_budget_tokens=1000)
        mgr.record_usage("agent-d", 700, 0)  # 70%
        with caplog.at_level(logging.WARNING):
            mgr.check_and_reserve("agent-d", 150)  # projected 850 = 85%
        assert any("utilization" in rec.message.lower() for rec in caplog.records)


# ---------- ComplianceGuard --------------------------------------------

class TestComplianceGuard:
    def setup_method(self):
        self.guard = ComplianceGuard()

    def test_guaranteed_approval_hard_block(self):
        result = self.guard.validate_response(
            "Congratulations — you have guaranteed approval on this loan!",
            agent_role="lead_nurturer",
        )
        assert result["passed"] is False
        assert result["escalation_required"] is True
        rules = [v["rule"] for v in result["violations"]]
        assert "guaranteed_approval" in rules

    def test_youre_approved_hard_block(self):
        result = self.guard.validate_response(
            "Great news, you're approved for the full amount.",
            agent_role="lead_nurturer",
        )
        assert result["passed"] is False
        assert any(v["regulation"] in ("TRID/UDAAP",) for v in result["violations"])

    def test_ecoa_prohibited_basis_hard_block(self):
        result = self.guard.validate_response(
            "We can offer you a better rate because you're married and Christian.",
            agent_role="rate_monitor",
        )
        assert result["passed"] is False
        assert result["escalation_required"] is True
        regs = {v["regulation"] for v in result["violations"]}
        assert "ECOA" in regs

    def test_apr_without_disclosure_hard_block(self):
        result = self.guard.validate_response(
            "Your APR of 6.5% is locked in.",
            agent_role="rate_monitor",
        )
        assert result["passed"] is False
        assert any(v["rule"] == "apr_without_disclosure" for v in result["violations"])

    def test_apr_with_disclosure_passes(self):
        result = self.guard.validate_response(
            "An APR of 6.5% is possible, subject to credit approval and final underwriting.",
            agent_role="rate_monitor",
        )
        assert result["passed"] is True

    def test_clean_response_passes(self):
        result = self.guard.validate_response(
            "Thanks for your interest! I'll have a loan officer reach out to discuss your options.",
            agent_role="receptionist",
        )
        assert result["passed"] is True
        assert result["violations"] == []
        assert result["escalation_required"] is False

    def test_best_rate_soft_warn(self):
        result = self.guard.validate_response(
            "We offer the best rate in town.",
            agent_role="rate_monitor",
        )
        # soft warn → passes but violations present
        assert result["passed"] is True
        assert any(v["rule"] == "best_rate_no_disclaimer" for v in result["violations"])

    def test_best_rate_with_disclaimer_no_warn(self):
        result = self.guard.validate_response(
            "We offer the best rate among lenders we surveyed today.",
            agent_role="rate_monitor",
        )
        assert result["passed"] is True
        assert not any(v["rule"] == "best_rate_no_disclaimer" for v in result["violations"])

    def test_fdcpa_threat_hard_block(self):
        result = self.guard.validate_response(
            "If you don't pay, we will sue and call your employer.",
            agent_role="collections",
        )
        assert result["passed"] is False
        assert any(v["regulation"] == "FDCPA" for v in result["violations"])

    def test_singleton_available(self):
        assert compliance_guard is not None


# ---------- HallucinationGuard -----------------------------------------

class TestHallucinationGuard:
    def setup_method(self):
        self.guard = HallucinationGuard()

    def test_unverified_currency_flagged(self):
        result = self.guard.verify_claims(
            "Your monthly payment will be $2,345.67.",
            context_data={"loan": {"monthly_payment": 1800.00}},
        )
        assert result["verified"] is False
        assert "$2,345.67" in result["unverified_claims"]
        assert result["confidence"] < 1.0

    def test_verified_currency_passes(self):
        result = self.guard.verify_claims(
            "Your monthly payment will be $1,800.",
            context_data={"loan": {"monthly_payment": "$1,800"}},
        )
        assert result["verified"] is True
        assert result["unverified_claims"] == []
        assert result["confidence"] == 1.0

    def test_unverified_percentage_flagged(self):
        result = self.guard.verify_claims(
            "Your interest rate is 7.25%.",
            context_data={"quoted_rate": "6.5%"},
        )
        assert result["verified"] is False
        assert any("7.25" in c for c in result["unverified_claims"])

    def test_no_claims_means_verified(self):
        result = self.guard.verify_claims(
            "Thanks for reaching out — I'll follow up with a loan officer.",
            context_data={"anything": 123},
        )
        assert result["verified"] is True
        assert result["confidence"] == 1.0

    def test_none_context_treats_all_as_unverified(self):
        result = self.guard.verify_claims(
            "Rate locked at 6.5% closing on 2026-05-19.",
            context_data=None,
        )
        assert result["verified"] is False
        assert len(result["unverified_claims"]) >= 2

    def test_recursive_context_walk(self):
        ctx = {"a": {"b": [{"c": "rate 5.5%"}]}}
        result = self.guard.verify_claims("Confirmed at 5.5%.", context_data=ctx)
        assert result["verified"] is True

    def test_singleton_available(self):
        assert hallucination_guard is not None
