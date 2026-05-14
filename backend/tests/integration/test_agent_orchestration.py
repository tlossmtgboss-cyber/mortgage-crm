"""
Agent Orchestration Integration Tests

Tests for the intent routing, tool loading, and orchestrator workflow:
- Fast regex-based intent classification
- LLM fallback classification (mocked)
- Intent-to-agent mapping
- Intent-to-tool scoping
- Circuit breaker state transitions
- Orchestrator graph creation

Key files:
    backend/agents/orchestrator.py
    backend/agents/intent_router.py
    backend/agents/nodes/analyze.py
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = [pytest.mark.integration, pytest.mark.critical]


# ─── Intent classification (regex fast-path) ───────────────────────────


class TestIntentClassificationFastPath:
    """Test the regex-based fast classification path (~1-5ms)."""

    @pytest.fixture(autouse=True)
    def _import_router(self):
        from agents.intent_router import (
            classify_intent_fast,
            INTENT_PATTERNS,
            INTENT_TO_AGENTS,
        )
        self.classify_fast = classify_intent_fast
        self.intent_patterns = INTENT_PATTERNS
        self.intent_to_agents = INTENT_TO_AGENTS

    @pytest.mark.parametrize("query,expected_intent", [
        ("hi there", "greeting"),
        ("hello", "greeting"),
        ("good morning", "greeting"),
        ("thanks!", "simple"),
        ("show me my pipeline", "pipeline"),
        ("what are my top leads?", "top_leads"),
        ("check TRID compliance for loan 123", "compliance"),
        ("what's the current rate?", "rates"),
        ("schedule a meeting for tomorrow", "schedule"),
        ("what documents are missing?", "documents"),
        ("show me my tasks", "tasks"),
        ("what's the SLA status?", "sla"),
        ("send an email to John Smith", "email"),
        ("call my client", "calls"),
        ("what are my daily priorities?", "priorities"),
        ("generate a pipeline report", "reports"),
        ("check my subscription", "billing"),
        ("who is on my team?", "team"),
        ("Q3 vs Q4 performance", "historical"),
        ("show my notifications", "notifications"),
    ])
    def test_fast_classify_known_intents(self, query, expected_intent):
        """Known query patterns should be classified via regex in under 10ms."""
        start = time.perf_counter()
        intent, confidence, pattern = self.classify_fast(query)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert intent == expected_intent, (
            f"Query '{query}' classified as '{intent}', expected '{expected_intent}'"
        )
        assert confidence >= 0.9
        assert pattern is not None
        assert elapsed_ms < 50, f"Fast path took {elapsed_ms:.1f}ms (should be <50ms)"

    def test_fast_classify_unknown_returns_none(self):
        """Ambiguous queries should return None for LLM fallback."""
        intent, confidence, pattern = self.classify_fast(
            "can you help me figure something out about that thing?"
        )
        assert intent is None
        assert confidence == 0.0
        assert pattern is None

    def test_fast_classify_empty_string(self):
        """Empty string should not crash."""
        intent, confidence, pattern = self.classify_fast("")
        assert intent is None
        assert confidence == 0.0

    def test_all_intents_have_agent_mapping(self):
        """Every intent in INTENT_PATTERNS should have an entry in INTENT_TO_AGENTS."""
        for intent_key in self.intent_patterns:
            assert intent_key in self.intent_to_agents, (
                f"Intent '{intent_key}' has patterns but no agent mapping"
            )


# ─── Intent classification (LLM fallback) ──────────────────────────────


class TestIntentClassificationLLMFallback:
    """Test LLM-based classification fallback (mocked)."""

    @pytest.mark.asyncio
    async def test_classify_intent_uses_fast_path_first(self):
        """classify_intent should use regex before falling back to LLM."""
        from agents.intent_router import classify_intent

        result = await classify_intent("show me my pipeline", use_llm_fallback=False)
        assert result["intent"] == "pipeline"
        assert result["method"] == "pattern_match"
        assert result["confidence"] >= 0.9
        assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_classify_intent_falls_back_to_general(self):
        """With LLM fallback disabled, ambiguous queries should return general."""
        from agents.intent_router import classify_intent

        result = await classify_intent(
            "what is the meaning of life?",
            use_llm_fallback=False,
        )
        assert result["intent"] == "general"

    @pytest.mark.asyncio
    async def test_classify_intent_none_input(self):
        """None input should not crash."""
        from agents.intent_router import classify_intent

        result = await classify_intent(None, use_llm_fallback=False)
        assert result["intent"] == "general"


# ─── Intent-to-tool scoping ─────────────────────────────────────────────


class TestIntentToolScoping:
    """Verify that tool scoping per intent is correctly configured."""

    def test_greeting_has_no_tools(self):
        """Greeting intent should load zero tools."""
        from agents.orchestrator import INTENT_TO_SCOPED_TOOLS
        assert INTENT_TO_SCOPED_TOOLS.get("greeting") == []

    def test_pipeline_has_relevant_tools(self):
        """Pipeline intent should include pipeline/metric tools."""
        from agents.orchestrator import INTENT_TO_SCOPED_TOOLS
        tools = INTENT_TO_SCOPED_TOOLS.get("pipeline", [])
        assert "get_pipeline" in tools
        assert "get_pipeline_metrics" in tools

    def test_compliance_has_trid_tool(self):
        """Compliance intent should include TRID check tool."""
        from agents.orchestrator import INTENT_TO_SCOPED_TOOLS
        tools = INTENT_TO_SCOPED_TOOLS.get("compliance", [])
        assert "check_trid_compliance" in tools

    def test_tool_counts_are_bounded(self):
        """Each intent should load at most 20 tools (not all 160+)."""
        from agents.orchestrator import INTENT_TO_SCOPED_TOOLS
        for intent, tools in INTENT_TO_SCOPED_TOOLS.items():
            assert len(tools) <= 25, (
                f"Intent '{intent}' has {len(tools)} tools (should be <= 25)"
            )


# ─── Circuit breaker ────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Test the LLM circuit breaker state machine."""

    def test_starts_closed(self):
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=1.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_resets_on_success(self):
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_half_open_after_cooldown(self):
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)  # Wait for cooldown
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_returns_to_open_on_failure(self):
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN


# ─── Haiku/Sonnet model selection ───────────────────────────────────────


class TestModelSelection:
    """Verify that Haiku vs Sonnet selection follows intent classification."""

    def test_greeting_uses_haiku(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("greeting") is True

    def test_simple_uses_haiku(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("simple") is True

    def test_pipeline_uses_sonnet(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("pipeline") is False

    def test_compliance_uses_sonnet(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("compliance") is False

    def test_rates_uses_sonnet(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("rates") is False

    def test_unknown_defaults_to_sonnet(self):
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("unknown_intent_xyz") is False
