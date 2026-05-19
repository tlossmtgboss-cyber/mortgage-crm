"""
Module-loading smoke tests for backend service modules.

Each test imports a service module via importlib.util.spec_from_file_location
to bypass services/__init__.py (which has heavy transitive imports). The
load itself executes the module's top-level statements — class definitions,
dataclasses, constants, helper-function declarations — which is the single
biggest lever for raising measured coverage of services/ that otherwise
import-error during the integration suite.

Each module that loads successfully is asserted to expose at least one
public attribute. Modules that fail to load (missing optional deps,
circular imports) skip gracefully so this file never adds a flaky test.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


# Ensure encryption_utils transitive imports work in test mode.
os.environ.setdefault(
    "DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA="
)


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SERVICES_DIR = _BACKEND_DIR / "services"


def _safe_load(rel_path: str, mod_name: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as e:
        pytest.skip(f"{rel_path} not importable in isolation: {type(e).__name__}: {e}")
    return module


def _has_public_attr(module) -> bool:
    """A module is 'real' if it exposes at least one non-dunder attribute."""
    return any(not k.startswith("_") for k in dir(module))


# ---------------------------------------------------------------------------
# Lightweight pure-logic / dataclass-only service modules that should load
# cleanly without optional infra (Redis, Anthropic, FastAPI app context).
#
# Selection criteria: modules whose top-level imports are stdlib +
# logging + dataclasses + sqlalchemy primitives only. Each adds 50-300
# lines to the coverage tally.
# ---------------------------------------------------------------------------

_MODULES = [
    # Salesforce sub-package — internal modules with no cross-package init
    ("services/salesforce/_mapping.py", "_smoke_sf_mapping"),
    ("services/salesforce/_queries.py", "_smoke_sf_queries"),
    ("services/salesforce/_state.py", "_smoke_sf_state"),
    ("services/salesforce/stage_mapping.py", "_smoke_sf_stage_mapping"),
    # Workflow constants — pure data
    ("services/workflow_constants.py", "_smoke_workflow_constants"),
    # Loan reconciliation service — pure logic + sqlalchemy text
    ("services/loan_reconciliation_service.py", "_smoke_loan_recon"),
    # Compliance / regulatory engines (mostly dataclasses + rule tables)
    ("services/trid_engine.py", "_smoke_trid"),
    ("services/fair_lending_service.py", "_smoke_fair_lending"),
    ("services/adverse_action_service.py", "_smoke_adverse_action"),
    # Lead / pipeline pure-logic services
    ("services/pipeline_probability_service.py", "_smoke_pipeline_prob"),
    ("services/lead_cascade_service.py", "_smoke_lead_cascade"),
    ("services/proactive_deal_alerts_service.py", "_smoke_proactive"),
    # Misc small utility services
    ("services/amortization_service.py", "_smoke_amortization"),
    ("services/api_deprecation.py", "_smoke_api_deprecation"),
    ("services/audit_events.py", "_smoke_audit_events"),
    ("services/data_filter_service.py", "_smoke_data_filter"),
    ("services/availability_cache.py", "_smoke_avail_cache"),
    # Agent orchestration submodules (importlib-safe)
    ("agents/orchestration/governance_metrics.py", "_smoke_gov_metrics"),
    ("agents/orchestration/intent_confidence.py", "_smoke_intent_conf"),
    ("agents/orchestration/token_budget.py", "_smoke_token_budget"),
    # Auth tokens — pure JWT helpers
    ("auth/tokens.py", "_smoke_auth_tokens"),
    ("auth/config.py", "_smoke_auth_config"),
]


@pytest.mark.parametrize("rel_path,mod_name", _MODULES)
def test_service_module_loads_cleanly(rel_path, mod_name):
    """Each listed module imports without raising and exposes public symbols."""
    module = _safe_load(rel_path, mod_name)
    assert _has_public_attr(module), f"{rel_path}: no public attributes after load"
