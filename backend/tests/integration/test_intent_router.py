"""
Integration tests for the intent-router confidence gate.

Wave 3 / D3 audit remediation #1 — verify that the new
``agents.orchestration.intent_confidence`` gate:

  * passes through high-confidence classifications,
  * rewrites low-confidence classifications to ``general_query``,
  * honours the ``INTENT_CONFIDENCE_THRESHOLD`` env var,
  * records a governance metric on fallback,
  * gracefully handles empty / malformed input.

Uses the same ``importlib.util.spec_from_file_location`` pattern as
``test_compliance_guard.py`` to avoid pulling in the full ``agents/``
package (which imports LangGraph and the entire agent fleet).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import List

import pytest


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Module loader — load intent_confidence by file path so we skip agents/__init__
# ---------------------------------------------------------------------------

def _load_intent_confidence() -> ModuleType:
    backend_dir = Path(__file__).resolve().parents[2]
    target = (
        backend_dir / "agents" / "orchestration" / "intent_confidence.py"
    )
    if not target.exists():  # pragma: no cover - safety net
        pytest.skip(f"intent_confidence.py not found at {target}")
    spec = importlib.util.spec_from_file_location(
        "_perennia_intent_confidence_under_test", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_ic = _load_intent_confidence()
apply_confidence_gate = _ic.apply_confidence_gate
get_threshold = _ic.get_threshold
FALLBACK_INTENT = _ic.FALLBACK_INTENT
FALLBACK_AGENTS = _ic.FALLBACK_AGENTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MetricSpy:
    """Stand-in for governance_metrics.record_compliance_event."""

    def __init__(self) -> None:
        self.calls: List[dict] = []

    def __call__(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.fixture
def metric_spy(monkeypatch) -> _MetricSpy:
    """Patch the gate's metric recorder so we can assert it was called."""
    spy = _MetricSpy()

    fake_module = ModuleType("_fake_governance_metrics")
    fake_module.record_compliance_event = spy  # type: ignore[attr-defined]

    # Inject into both possible import paths the gate tries.
    monkeypatch.setitem(
        sys.modules, "agents.orchestration.governance_metrics", fake_module
    )
    monkeypatch.setitem(
        sys.modules, "services.governance_metrics", fake_module
    )
    return spy


@pytest.fixture(autouse=True)
def _reset_threshold(monkeypatch):
    """Make sure each test starts from the default threshold."""
    monkeypatch.delenv("INTENT_CONFIDENCE_THRESHOLD", raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. High-confidence classification routes to the correct agent
# ---------------------------------------------------------------------------

def test_high_confidence_passes_through(metric_spy):
    classification = {
        "intent": "leads",
        "confidence": 0.95,
        "agents": ["lead_nurturer"],
        "method": "pattern_match",
    }
    out = apply_confidence_gate(classification, query="who should I call?")

    assert out["intent"] == "leads"
    assert out["agents"] == ["lead_nurturer"]
    assert out["fallback_applied"] is False
    # No governance event should fire on a clean route.
    assert metric_spy.calls == []


# ---------------------------------------------------------------------------
# 2. Low-confidence classification falls back to general_query
# ---------------------------------------------------------------------------

def test_low_confidence_falls_back_to_general_query(metric_spy):
    classification = {
        "intent": "rates",
        "confidence": 0.42,  # below the 0.75 default threshold
        "agents": ["rate_advisor"],
        "method": "llm",
    }
    out = apply_confidence_gate(
        classification, query="hmmm uhhh thing about money idk"
    )

    assert out["intent"] == FALLBACK_INTENT == "general_query"
    assert out["agents"] == FALLBACK_AGENTS
    assert out["fallback_applied"] is True
    assert out["original_intent"] == "rates"
    assert out["original_confidence"] == 0.42


# ---------------------------------------------------------------------------
# 3. Threshold is overridable via env var
# ---------------------------------------------------------------------------

def test_threshold_is_env_overridable(monkeypatch, metric_spy):
    # A classification with 0.80 confidence passes the default 0.75 gate...
    classification = {
        "intent": "schedule",
        "confidence": 0.80,
        "agents": ["smart_scheduler"],
        "method": "pattern_match",
    }
    out = apply_confidence_gate(classification, query="book me a call")
    assert out["fallback_applied"] is False
    assert out["intent"] == "schedule"

    # ...but if we raise the bar to 0.90, the same classification falls back.
    monkeypatch.setenv("INTENT_CONFIDENCE_THRESHOLD", "0.90")
    assert get_threshold() == pytest.approx(0.90)

    out = apply_confidence_gate(classification, query="book me a call")
    assert out["fallback_applied"] is True
    assert out["intent"] == FALLBACK_INTENT


# ---------------------------------------------------------------------------
# 4. Metrics are recorded on fallback
# ---------------------------------------------------------------------------

def test_metrics_recorded_on_low_confidence_fallback(metric_spy):
    classification = {
        "intent": "documents",
        "confidence": 0.20,
        "agents": ["document_tracker"],
        "method": "llm",
    }
    apply_confidence_gate(classification, query="...")

    assert len(metric_spy.calls) == 1
    call = metric_spy.calls[0]
    assert call["violation_type"] == "low_confidence_intent"
    details = call["details"]
    assert details["chosen_intent"] == "documents"
    assert details["confidence"] == pytest.approx(0.20)
    assert details["fallback_intent"] == FALLBACK_INTENT
    assert "threshold" in details


# ---------------------------------------------------------------------------
# 5. Empty / null input is handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_input",
    [None, {}, {"intent": None, "confidence": None}, "not-a-dict"],
)
def test_empty_or_null_input_falls_back(bad_input, metric_spy):
    out = apply_confidence_gate(bad_input, query="")

    assert out["intent"] == FALLBACK_INTENT
    assert out["agents"] == FALLBACK_AGENTS
    assert out["fallback_applied"] is True
    # The gate must never raise on malformed input.
