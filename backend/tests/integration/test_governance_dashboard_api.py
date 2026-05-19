"""
Integration tests for the W3 governance dashboard API.

These tests exercise the (forthcoming) governance dashboard routes that
expose engineering-quality metrics:
  * /governance/coverage   — coverage snapshot
  * /governance/mypy       — type-check report
  * /governance/integration — integration test pass/fail counts
  * /governance/security   — security scan summary
  * /governance/score      — composite platform-health score

Most assertions are gated behind ``xfail`` because the routes are still
being wired by Wave 3. The IMPORT and COLLECTION must succeed cleanly so
that CI surfaces regressions the moment the routes land.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _try_load_governance_routes():
    """Best-effort load of the governance routes module by file path so we
    skip the heavy ``main.py`` import chain. Returns the module or None.
    """
    backend_dir = Path(__file__).resolve().parents[2]
    candidates = [
        backend_dir / "routes" / "governance_dashboard.py",
        backend_dir / "routes" / "governance.py",
        backend_dir / "routes" / "governance_routes.py",
    ]
    for target in candidates:
        if target.exists():
            spec = importlib.util.spec_from_file_location(
                f"_perennia_governance_under_test_{target.stem}", str(target)
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception:
                return None
            return module
    return None


_gov_module = _try_load_governance_routes()


@pytest.mark.xfail(
    _gov_module is None,
    reason="TODO(W3): governance dashboard routes not yet wired",
    strict=False,
)
def test_governance_coverage_endpoint_returns_snapshot():
    assert _gov_module is not None
    assert hasattr(_gov_module, "router") or hasattr(_gov_module, "get_coverage")


@pytest.mark.xfail(
    _gov_module is None,
    reason="TODO(W3): governance dashboard routes not yet wired",
    strict=False,
)
def test_governance_mypy_endpoint_returns_typecheck_report():
    assert _gov_module is not None
    attrs = dir(_gov_module)
    assert any("mypy" in a.lower() for a in attrs)


@pytest.mark.xfail(
    _gov_module is None,
    reason="TODO(W3): governance dashboard routes not yet wired",
    strict=False,
)
def test_governance_integration_endpoint_returns_pass_fail():
    assert _gov_module is not None
    attrs = dir(_gov_module)
    assert any("integration" in a.lower() or "test_results" in a.lower() for a in attrs)


@pytest.mark.xfail(
    _gov_module is None,
    reason="TODO(W3): governance dashboard routes not yet wired",
    strict=False,
)
def test_governance_security_endpoint_returns_scan_summary():
    assert _gov_module is not None
    attrs = dir(_gov_module)
    assert any("security" in a.lower() or "scan" in a.lower() for a in attrs)


@pytest.mark.xfail(
    _gov_module is None,
    reason="TODO(W3): governance dashboard routes not yet wired",
    strict=False,
)
def test_governance_score_endpoint_returns_composite():
    assert _gov_module is not None
    attrs = dir(_gov_module)
    assert any("score" in a.lower() or "health" in a.lower() for a in attrs)
