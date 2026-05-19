"""
Integration tests for intent router classification.

Targets backend/agents/intent_router.py — fast-path regex matching, empty
input fallback, response metadata schema, and the per-intent agent mapping.
The LLM fallback path is exercised with a stub Anthropic client so no real
API calls occur.

Loaded via importlib to avoid pulling the full agents/__init__ (which imports
the agent fleet + LangGraph).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_intent_router():
    target = _BACKEND_DIR / "agents" / "intent_router.py"
    if not target.exists():
        pytest.skip("intent_router.py missing")
    # Create a stub package so the module's relative imports
    # (.anthropic_client, .consolidation, .orchestration.intent_confidence)
    # resolve without dragging in the agent fleet.
    pkg_name = "_perennia_agents_pkg"
    pkg = ModuleType(pkg_name)
    pkg.__path__ = [str(_BACKEND_DIR / "agents")]
    sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.intent_router",
        str(target),
        submodule_search_locations=None,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_ir = _load_intent_router()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify(query: str, **kw) -> dict:
    """Sync wrapper around the async classify_intent for cleaner tests."""
    return asyncio.run(_ir.classify_intent(query, **kw, apply_gate=False))


# ---------------------------------------------------------------------------
# Test 1: Greeting → greeting intent (fast pattern match)
# ---------------------------------------------------------------------------

def test_greeting_classified_to_greeting():
    result = _classify("hello there", use_llm_fallback=False)
    assert result["intent"] == "greeting"
    assert result["method"] == "pattern_match"


# ---------------------------------------------------------------------------
# Test 2: Pipeline query → pipeline intent
# ---------------------------------------------------------------------------

def test_pipeline_query_classified_to_pipeline():
    result = _classify("show me the loan pipeline status", use_llm_fallback=False)
    assert result["intent"] == "pipeline"


# ---------------------------------------------------------------------------
# Test 3: Compliance query → compliance intent
# ---------------------------------------------------------------------------

def test_compliance_query_classified_to_compliance():
    result = _classify("check TRID disclosure compliance", use_llm_fallback=False)
    assert result["intent"] == "compliance"


# ---------------------------------------------------------------------------
# Test 4: Schedule query → schedule intent
# ---------------------------------------------------------------------------

def test_schedule_query_classified_to_schedule():
    result = _classify("schedule a meeting tomorrow at 3pm", use_llm_fallback=False)
    assert result["intent"] == "schedule"


# ---------------------------------------------------------------------------
# Test 5: Compound query (text X AND schedule Y) routes to compound
# ---------------------------------------------------------------------------

def test_compound_query_classified_to_compound():
    result = _classify(
        "send a text to John and schedule a meeting for Friday",
        use_llm_fallback=False,
    )
    assert result["intent"] == "compound"


# ---------------------------------------------------------------------------
# Test 6: Empty input falls back to general (skips LLM path entirely)
# ---------------------------------------------------------------------------

def test_empty_input_falls_back_to_general():
    result = _classify("", use_llm_fallback=False)
    assert result["intent"] == "general"
    assert result["method"] == "fallback"


# ---------------------------------------------------------------------------
# Test 7: None input is handled defensively
# ---------------------------------------------------------------------------

def test_none_input_falls_back_to_general():
    result = asyncio.run(
        _ir.classify_intent(None, use_llm_fallback=False, apply_gate=False)
    )
    assert result["intent"] == "general"


# ---------------------------------------------------------------------------
# Test 8: Response payload always contains the expected keys
# ---------------------------------------------------------------------------

def test_response_metadata_schema():
    result = _classify("hello", use_llm_fallback=False)
    for key in ("intent", "confidence", "agents", "method",
                "matched_pattern", "elapsed_ms"):
        assert key in result


# ---------------------------------------------------------------------------
# Test 9: classify_intent_fast returns None on no match
# ---------------------------------------------------------------------------

def test_classify_intent_fast_no_match_returns_none():
    intent, conf, pattern = _ir.classify_intent_fast(
        "xqzqz random nonsense words abc123"
    )
    assert intent is None
    assert conf == 0.0
    assert pattern is None


# ---------------------------------------------------------------------------
# Test 10: LLM fallback path uses provided stub client (no real API call)
# ---------------------------------------------------------------------------

def test_llm_fallback_path_uses_stub_client():
    class _StubResponse:
        def __init__(self, intent: str):
            self.content = [SimpleNamespace(text=intent)]

    class _StubMessages:
        def create(self, **kwargs):
            return _StubResponse("tasks")

    class _StubClient:
        messages = _StubMessages()

    result = asyncio.run(
        _ir.classify_intent(
            "completely unmatched query xyz",
            anthropic_client=_StubClient(),
            use_llm_fallback=True,
            apply_gate=False,
        )
    )
    # Stub returns "tasks" — confirm the LLM branch ran.
    assert result["method"] == "llm"
    assert result["intent"] == "tasks"
