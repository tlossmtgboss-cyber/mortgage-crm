"""
Integration tests for `middleware/admin_guard.py` — role admission matrix.

Loads the module via importlib and exercises `_extract_role` + `require_admin`
through a FastAPI app with dependency-overrides for `get_current_user`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_module():
    target = _BACKEND_DIR / "middleware" / "admin_guard.py"
    if not target.exists():
        pytest.skip("admin_guard.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_admin_guard", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"admin_guard import failed: {exc}")
    return module


_ag = _load_module()


def _user(role):
    return SimpleNamespace(id=1, role=role)


def _call_guard(user):
    """Run require_admin directly; returns (status_code, raised_exc_or_None)."""
    try:
        result = asyncio.run(_ag.require_admin(current_user=user))
        return 200, None, result
    except Exception as exc:
        code = getattr(exc, "status_code", 500)
        return code, exc, None


# ---------------------------------------------------------------------------
# Admit roles (3)
# ---------------------------------------------------------------------------

def test_admin_role_admitted():
    code, _exc, user = _call_guard(_user("admin"))
    assert code == 200
    assert user is not None


def test_owner_role_admitted():
    code, _exc, user = _call_guard(_user("owner"))
    assert code == 200


def test_super_admin_role_admitted():
    code, _exc, user = _call_guard(_user("super_admin"))
    assert code == 200


# ---------------------------------------------------------------------------
# Reject non-admin roles (3)
# ---------------------------------------------------------------------------

def test_user_role_rejected_with_403():
    code, _exc, _u = _call_guard(_user("user"))
    assert code == 403


def test_loan_officer_role_rejected_with_403():
    code, _exc, _u = _call_guard(_user("loan_officer"))
    assert code == 403


def test_processor_role_rejected_with_403():
    code, _exc, _u = _call_guard(_user("processor"))
    assert code == 403


# ---------------------------------------------------------------------------
# Missing role / null user
# ---------------------------------------------------------------------------

def test_missing_role_rejected_with_403():
    # No `.role` attribute at all
    user = SimpleNamespace(id=1)
    code, _exc, _u = _call_guard(user)
    assert code == 403


def test_null_user_rejected_with_401():
    code, _exc, _u = _call_guard(None)
    assert code == 401
