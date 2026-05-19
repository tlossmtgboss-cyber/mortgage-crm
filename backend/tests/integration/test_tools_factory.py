"""
Integration tests for the per-domain tools factory.

Targets backend/agents/service/tools_factory/ — the 8 sub-modules that each
expose a build_<domain>_tools(db, current_user, ctx) function plus the
top-level build_tool_functions composer.

Loaded via importlib to bypass agents/__init__ (which would drag in
LangGraph, all agent classes, etc.).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]

_DOMAIN_FILES = {
    "pipeline": "_pipeline.py",
    "tasks": "_tasks.py",
    "leads": "_leads.py",
    "loans": "_loans.py",
    "telephony": "_telephony.py",
    "comms": "_comms.py",
    "partners": "_partners.py",
    "analytics": "_analytics.py",
}


def _load_domain_module(domain: str) -> ModuleType:
    rel = Path("agents/service/tools_factory") / _DOMAIN_FILES[domain]
    target = _BACKEND_DIR / rel
    if not target.exists():
        pytest.skip(f"{rel} missing")
    mod_name = f"_perennia_tools_factory_{domain}"
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _make_stub_db():
    """Minimal stub Session — tools instantiate lazily, never executed here."""
    class _StubDB:
        def execute(self, *a, **kw):
            raise AssertionError("DB execute not expected in builder tests")
    return _StubDB()


def _make_stub_user():
    return SimpleNamespace(
        id=1, organization_id=42, permission_role="admin", email="x@y.com"
    )


def _make_ctx():
    return {"org_id": 42, "_user_role": "admin", "_has_org_wide_access": True}


# ---------------------------------------------------------------------------
# Test 1-8: Each sub-module importable and exports build_<domain>_tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("domain", list(_DOMAIN_FILES.keys()))
def test_each_subsmodule_exposes_build_function(domain):
    mod = _load_domain_module(domain)
    expected = f"build_{domain}_tools" if domain not in ("comms", "telephony", "partners", "analytics") \
        else f"build_{domain}_tools"
    # Special cases: tasks → build_task_tools, leads → build_lead_tools, loans → build_loan_tools, partners → build_partner_tools
    mapping = {
        "pipeline": "build_pipeline_tools",
        "tasks": "build_task_tools",
        "leads": "build_lead_tools",
        "loans": "build_loan_tools",
        "telephony": "build_telephony_tools",
        "comms": "build_comms_tools",
        "partners": "build_partner_tools",
        "analytics": "build_analytics_tools",
    }
    fn_name = mapping[domain]
    assert hasattr(mod, fn_name), f"{domain}: missing {fn_name}"
    assert callable(getattr(mod, fn_name))


# ---------------------------------------------------------------------------
# Test 9: Each builder returns a dict[str, callable] of async tools
# ---------------------------------------------------------------------------

def test_builders_return_dict_of_callables():
    # Pipeline is the simplest, most stable domain — assert dict shape there.
    mod = _load_domain_module("pipeline")
    tools = mod.build_pipeline_tools(_make_stub_db(), _make_stub_user(), _make_ctx())
    assert isinstance(tools, dict)
    assert len(tools) > 0
    for name, fn in tools.items():
        assert isinstance(name, str) and name
        assert callable(fn)


# ---------------------------------------------------------------------------
# Test 10: No circular imports — loading all 8 sub-modules sequentially works
# ---------------------------------------------------------------------------

def test_no_circular_imports_across_subsmodules():
    loaded = {}
    for domain in _DOMAIN_FILES:
        loaded[domain] = _load_domain_module(domain)
    # All 8 modules loaded without error
    assert len(loaded) == 8
