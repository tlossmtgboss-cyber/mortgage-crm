"""
Integration tests for the multi-state UPL Rules Engine.

Loads the engine via file path so we don't drag in the heavy
``services/__init__`` chain (and its DB imports). Tests are pure, fast
and deterministic.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _load_engine():
    backend_dir = Path(__file__).resolve().parents[2]
    target = backend_dir / "services" / "compliance" / "upl_rules_engine.py"
    if not target.exists():  # pragma: no cover
        pytest.skip(f"upl_rules_engine.py not found at {target}")
    spec = importlib.util.spec_from_file_location(
        "_perennia_upl_engine_under_test", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_mod = _load_engine()
UPLRulesEngine = _mod.UPLRulesEngine
upl_rules_engine = _mod.upl_rules_engine
STATE_RULES_VERSION = _mod.STATE_RULES_VERSION
DEFAULT_RESTRICTIONS = _mod.DEFAULT_RESTRICTIONS


@pytest.fixture
def engine() -> UPLRulesEngine:
    return upl_rules_engine


# --------------------------------------------------------------------- CA

def test_ca_blocks_legal_advice(engine):
    res = engine.check("provide_legal_advice", "CA", context={})
    assert res["allowed"] is False
    assert res["state"] == "CA"
    assert "no_legal_advice" in res["restrictions"]
    assert any("§6125" in c for c in res["regulatory_citations"])
    assert res["state_rules_version"] == STATE_RULES_VERSION


# --------------------------------------------------------------------- NY

def test_ny_blocks_lien_priority_discussion(engine):
    res = engine.check("discuss_lien_priority", "NY", context={})
    assert res["allowed"] is False
    assert "no_lien_priority_interpretation" in res["restrictions"]
    assert "written_attorney_referral_on_file" in res["required_disclosures"]
    assert any("§484" in c for c in res["regulatory_citations"])


# --------------------------------------------------------------------- TX

def test_tx_requires_trec_disclosure(engine):
    rule = engine.get_rule_set("TX")
    assert (
        "trec_information_about_brokerage_services_for_residential"
        in rule["required_disclosures"]
    )
    # TX still blocks raw legal advice
    res = engine.check("provide_legal_advice", "TX")
    assert res["allowed"] is False


# --------------------------------------------------------------------- FL

def test_fl_blocks_contract_interpretation(engine):
    res = engine.check("interpret_contract_terms", "FL")
    assert res["allowed"] is False
    assert "no_contract_term_interpretation" in res["restrictions"]
    assert (
        "client_acknowledgement_of_non_attorney_role"
        in res["required_disclosures"]
    )


# --------------------------------------------------------------------- IL

def test_il_blocks_payoff_negotiation(engine):
    res = engine.check("negotiate_payoff_terms", "IL")
    assert res["allowed"] is False
    assert "no_payoff_negotiation_with_third_parties" in res["restrictions"]
    # but tax_advice check returns blocked because of no_tax_advice default
    res2 = engine.check("give_tax_advice", "IL")
    assert res2["allowed"] is False


# --------------------------------------------------------------------- defaults

def test_default_state_uses_conservative_restrictions(engine):
    rule = engine.get_rule_set("GA")
    assert rule["modeled"] is False
    for r in DEFAULT_RESTRICTIONS:
        assert r in rule["restrictions"]
    assert "non_attorney_role" in rule["required_disclosures"]


def test_unknown_state_returns_conservative_default(engine):
    rule = engine.get_rule_set("ZZ")
    assert rule["state"] == "ZZ"
    assert "no_legal_advice" in rule["restrictions"]
    # Action checks against unmodeled state block legal advice
    res = engine.check("provide_legal_advice", "ZZ")
    assert res["allowed"] is False


def test_puerto_rico_and_usvi_are_covered(engine):
    states = engine.list_states()
    assert "PR" in states
    assert "USVI" in states
    pr_rule = engine.get_rule_set("PR")
    usvi_rule = engine.get_rule_set("USVI")
    assert "no_legal_advice" in pr_rule["restrictions"]
    assert "no_legal_advice" in usvi_rule["restrictions"]


# --------------------------------------------------------------------- shape

def test_check_response_shape(engine):
    res = engine.check("provide_legal_advice", "CA")
    for key in (
        "allowed",
        "action",
        "state",
        "restrictions",
        "warnings",
        "required_disclosures",
        "regulatory_citations",
        "state_rules_version",
    ):
        assert key in res, f"missing key {key}"
    assert isinstance(res["restrictions"], list)
    assert isinstance(res["warnings"], list)


def test_rule_set_response_shape(engine):
    rule = engine.get_rule_set("NY")
    for key in (
        "state",
        "state_rules_version",
        "restrictions",
        "warnings",
        "required_disclosures",
        "regulatory_citations",
        "last_updated",
    ):
        assert key in rule


def test_unknown_action_is_rejected_conservatively(engine):
    res = engine.check("hack_the_planet", "CA")
    assert res["allowed"] is False
    assert any("Unknown action" in w for w in res["warnings"])


def test_disclosure_timing_guidance_allowed_in_modeled_states(engine):
    # Disclosure timing guidance is generally permissible per CFPB; modeled
    # states should not block it.
    for st in ("CA", "NY", "TX", "FL", "IL"):
        res = engine.check("provide_disclosure_timing_guidance", st)
        assert res["allowed"] is True, f"{st} unexpectedly blocked"
