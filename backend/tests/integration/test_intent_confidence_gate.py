"""
Integration tests for `agents/orchestration/intent_confidence.py`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_gate():
    target = _BACKEND_DIR / "agents" / "orchestration" / "intent_confidence.py"
    if not target.exists():
        pytest.skip("intent_confidence.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_intent_confidence", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_gate = _load_gate()


# ---------------------------------------------------------------------------
# 1. High-confidence pass-through
# ---------------------------------------------------------------------------

def test_high_confidence_passes_through():
    result = _gate.apply_confidence_gate(
        {"intent": "rate_quote", "confidence": 0.95, "agents": ["rate_monitor"]},
        query="what is the rate today",
    )
    assert result["intent"] == "rate_quote"
    assert result["fallback_applied"] is False


# ---------------------------------------------------------------------------
# 2. Low-confidence triggers fallback
# ---------------------------------------------------------------------------

def test_low_confidence_triggers_fallback():
    result = _gate.apply_confidence_gate(
        {"intent": "rate_quote", "confidence": 0.2, "agents": ["rate_monitor"]},
        query="hmm",
    )
    assert result["intent"] == _gate.FALLBACK_INTENT
    assert result["fallback_applied"] is True


# ---------------------------------------------------------------------------
# 3. Threshold env-overridable
# ---------------------------------------------------------------------------

def test_threshold_env_overridable(monkeypatch):
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.5")
    assert _gate.get_threshold() == 0.5
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.9")
    assert _gate.get_threshold() == 0.9


# ---------------------------------------------------------------------------
# 4. Metric emit on fallback — at minimum the function call does not raise
# ---------------------------------------------------------------------------

def test_metric_emit_on_fallback_does_not_raise():
    # Force fallback path and ensure the metrics-emit branch executes safely.
    result = _gate.apply_confidence_gate(
        {"intent": "x", "confidence": 0.1},
        query="abc",
    )
    assert result["fallback_applied"] is True


# ---------------------------------------------------------------------------
# 5. Null input → fallback
# ---------------------------------------------------------------------------

def test_null_input_triggers_fallback():
    result = _gate.apply_confidence_gate(None, query="hi")
    assert result["fallback_applied"] is True


# ---------------------------------------------------------------------------
# 6. Empty input → fallback
# ---------------------------------------------------------------------------

def test_empty_dict_triggers_fallback():
    result = _gate.apply_confidence_gate({}, query="")
    assert result["fallback_applied"] is True


# ---------------------------------------------------------------------------
# 7. Missing confidence field → fallback (is_low_confidence treats None as low)
# ---------------------------------------------------------------------------

def test_missing_confidence_triggers_fallback():
    result = _gate.apply_confidence_gate({"intent": "x"}, query="abc")
    assert result["fallback_applied"] is True


# ---------------------------------------------------------------------------
# 8. Threshold edge cases (exactly at boundary)
# ---------------------------------------------------------------------------

def test_confidence_exactly_at_threshold_passes(monkeypatch):
    """Exactly at threshold should pass (gate uses strict <)."""
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.5")
    result = _gate.apply_confidence_gate(
        {"intent": "x", "confidence": 0.5, "agents": ["a"]},
        query="",
        threshold=0.5,
    )
    # confidence == threshold is NOT low (strict <)
    assert result["fallback_applied"] is False
