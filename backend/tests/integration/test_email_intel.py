"""
Integration tests for AI email intelligence helpers.

Covers the pure-logic surface of services/ai_email_intelligence.py:
  - ECOA compliance validator: blocks prohibited demographic patterns
  - Token budget enforcer: truncates oversized prompts
  - Circuit breaker state transitions
  - Industry benchmark constants
  - Valid trigger event types
  - _safe_decimal helper
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_email = _load("_pa_email_intel", "services/ai_email_intelligence.py")


# ---------------------------------------------------------------------------
# ECOA compliance validator
# ---------------------------------------------------------------------------

def test_ecoa_clean_text_passes():
    ok, violations = _email._validate_ecoa_compliance(
        "Your loan application has been received and is being processed."
    )
    assert ok is True
    assert violations == []


def test_ecoa_marital_status_blocked():
    ok, violations = _email._validate_ecoa_compliance(
        "Congratulations on getting married — let us know your new spouse details."
    )
    assert ok is False
    assert len(violations) >= 1


def test_ecoa_race_term_blocked():
    ok, violations = _email._validate_ecoa_compliance(
        "Please update your race information for HMDA compliance."
    )
    assert ok is False
    assert any("VIOLATION" in v for v in violations)


def test_ecoa_religion_term_blocked():
    ok, violations = _email._validate_ecoa_compliance(
        "We offer faith-based financial counseling at our local mosque."
    )
    assert ok is False


def test_ecoa_disability_term_blocked():
    ok, violations = _email._validate_ecoa_compliance(
        "We accommodate borrowers with a disability."
    )
    assert ok is False


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

def test_token_budget_no_truncation_when_small():
    sys_p, usr_p = _email._enforce_token_budget("system small", "user small")
    assert sys_p == "system small"
    assert usr_p == "user small"


def test_token_budget_truncates_oversized():
    big_sys = "S\n" * 5000  # 10K chars
    big_usr = "U\n" * 5000
    sys_p, usr_p = _email._enforce_token_budget(big_sys, big_usr)
    assert len(sys_p) + len(usr_p) <= _email._MAX_PROMPT_CHARS + 100  # truncation suffix
    assert "[...truncated]" in sys_p or "[...truncated]" in usr_p


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

def test_circuit_breaker_starts_closed():
    # Reset to ensure clean state
    _email._circuit_record_success()
    assert _email._circuit_is_open() is False


def test_circuit_breaker_opens_after_threshold():
    _email._circuit_record_success()  # reset
    for _ in range(_email._CIRCUIT_FAILURE_THRESHOLD):
        _email._circuit_record_failure()
    assert _email._circuit_is_open() is True


def test_circuit_breaker_resets_on_success():
    _email._circuit_record_failure()
    _email._circuit_record_failure()
    _email._circuit_record_success()
    assert _email._circuit_is_open() is False


# ---------------------------------------------------------------------------
# Benchmark constants
# ---------------------------------------------------------------------------

def test_benchmark_best_days_tue_wed_thu():
    # 1=Tue, 2=Wed, 3=Thu (0=Mon)
    assert _email.BENCHMARK_BEST_DAYS == {1, 2, 3}


def test_benchmark_best_hours_10_to_1pm():
    hours = list(_email.BENCHMARK_BEST_HOURS)
    assert 10 in hours
    assert 14 not in hours  # 2pm not included (range exclusive at 14)


def test_benchmark_fallback_tuesday_10am():
    assert _email.BENCHMARK_FALLBACK_WEEKDAY == 1
    assert _email.BENCHMARK_FALLBACK_HOUR == 10


# ---------------------------------------------------------------------------
# Trigger registry
# ---------------------------------------------------------------------------

def test_trigger_rate_drop_is_valid():
    assert _email.TRIGGER_RATE_DROP in _email.VALID_TRIGGERS


def test_valid_triggers_has_6_kinds():
    assert len(_email.VALID_TRIGGERS) == 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_safe_decimal_none_passthrough():
    assert _email._safe_decimal(None) is None


def test_safe_decimal_numeric_conversion():
    assert _email._safe_decimal("123.45") == 123.45
    assert _email._safe_decimal(7) == 7.0


def test_safe_decimal_invalid_returns_none():
    assert _email._safe_decimal("not-a-number") is None
