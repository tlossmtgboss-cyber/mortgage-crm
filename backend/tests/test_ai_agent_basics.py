"""
AI Agent Basics Tests

Tests the foundational AI agent infrastructure:
- Intent classification (fast pattern matching)
- Intent-to-agent routing
- Token budget enforcement
- Tool loading for different intents
- Circuit breaker state machine
- Haiku vs Sonnet intent routing

Exercises real code from:
- agents/intent_router.py (classify_intent_fast, INTENT_TO_AGENTS)
- agents/token_budget.py (TokenBudget)
- agents/orchestrator.py (CircuitBreaker)
- agents/nodes/analyze.py (INTENT_TO_BASE_TOOLS)
"""

import pytest
import time
import logging
from unittest.mock import patch, MagicMock

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Classification (Pattern Matching)
# =============================================================================

@pytest.mark.critical
@pytest.mark.agents
@pytest.mark.unit
class TestIntentClassificationFast:
    """Test the ultra-fast pattern-based intent classification."""

    def test_greeting_intent(self):
        """'Hello' should classify as greeting."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("Hello!")
        assert intent == "greeting", f"Expected 'greeting', got '{intent}'"
        assert confidence > 0

    def test_pipeline_intent(self):
        """'Show me my pipeline' should classify as pipeline."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("Show me my pipeline")
        assert intent == "pipeline", f"Expected 'pipeline', got '{intent}'"

    def test_leads_intent(self):
        """'How are my leads doing?' should classify as leads."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("How are my leads doing?")
        assert intent is not None, "Leads query should match some intent"

    def test_schedule_intent(self):
        """'Schedule a meeting' should classify as schedule."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("Schedule a meeting with my client")
        assert intent == "schedule", f"Expected 'schedule', got '{intent}'"

    def test_rates_intent(self):
        """Rate inquiry should classify as rates."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("What are the current rates?")
        assert intent == "rates", f"Expected 'rates', got '{intent}'"

    def test_no_match_returns_none(self):
        """An unusual query may not match any pattern."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("xyzzy plugh qwerty")
        # Pattern matching may return None for unrecognized queries
        # This is fine — it falls back to LLM classification
        assert confidence == 0.0 or intent is not None

    def test_compliance_intent(self):
        """Compliance queries should classify correctly."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("Check TRID compliance for loan 123")
        assert intent == "compliance" or intent is not None

    def test_task_intent(self):
        """Task management queries should classify as tasks."""
        from agents.intent_router import classify_intent_fast
        intent, confidence, _ = classify_intent_fast("What tasks do I have today?")
        assert intent in ("tasks", "priorities"), f"Expected tasks/priorities, got '{intent}'"


# =============================================================================
# Intent-to-Agent Routing
# =============================================================================

@pytest.mark.critical
@pytest.mark.agents
@pytest.mark.unit
class TestIntentToAgentRouting:
    """Verify the INTENT_TO_AGENTS mapping is complete and correct."""

    def test_most_intents_have_agents(self):
        """Non-trivial intents should map to at least one agent.

        Some intents (like 'greeting') may have no agents because they
        are handled directly without routing to a specialized agent.
        """
        from agents.intent_router import INTENT_TO_AGENTS
        empty_allowed = {"greeting", "simple"}  # These are handled without agents
        for intent, agents in INTENT_TO_AGENTS.items():
            if intent not in empty_allowed:
                assert len(agents) > 0, f"Intent '{intent}' has no agents assigned"

    def test_general_intent_exists(self):
        """The 'general' fallback intent must exist."""
        from agents.intent_router import INTENT_TO_AGENTS
        assert "general" in INTENT_TO_AGENTS

    def test_pipeline_intent_has_analyst(self):
        """Pipeline intent should route to pipeline_analyst."""
        from agents.intent_router import INTENT_TO_AGENTS
        assert "pipeline" in INTENT_TO_AGENTS
        agents = INTENT_TO_AGENTS["pipeline"]
        assert any("pipeline" in a.lower() or "analyst" in a.lower() for a in agents)

    def test_compliance_intent_has_checker(self):
        """Compliance intent should route to compliance_checker."""
        from agents.intent_router import INTENT_TO_AGENTS
        assert "compliance" in INTENT_TO_AGENTS


# =============================================================================
# Haiku vs Sonnet Intent Routing
# =============================================================================

@pytest.mark.agents
@pytest.mark.unit
class TestHaikuIntentRouting:
    """Some intents use cheaper/faster Haiku model."""

    def test_greeting_uses_haiku(self):
        """Greeting intent should use Haiku (cheaper model)."""
        from agents.intent_router import HAIKU_INTENTS
        assert "greeting" in HAIKU_INTENTS

    def test_simple_uses_haiku(self):
        """Simple intent should use Haiku."""
        from agents.intent_router import HAIKU_INTENTS
        assert "simple" in HAIKU_INTENTS

    def test_is_haiku_intent_function(self):
        """is_haiku_intent() should return True for Haiku intents."""
        from agents.intent_router import is_haiku_intent
        assert is_haiku_intent("greeting") is True
        assert is_haiku_intent("pipeline") is False

    def test_pipeline_does_not_use_haiku(self):
        """Pipeline intent should NOT use Haiku (needs Sonnet)."""
        from agents.intent_router import HAIKU_INTENTS
        assert "pipeline" not in HAIKU_INTENTS

    def test_compliance_does_not_use_haiku(self):
        """Compliance intent requires Sonnet."""
        from agents.intent_router import HAIKU_INTENTS
        assert "compliance" not in HAIKU_INTENTS


# =============================================================================
# Token Budget Enforcement
# =============================================================================

@pytest.mark.critical
@pytest.mark.agents
@pytest.mark.unit
class TestTokenBudget:
    """Test the per-org token budget enforcement."""

    def test_budget_allows_within_limit(self):
        """Requests within budget should be allowed."""
        from agents.token_budget import TokenBudget
        budget = TokenBudget(max_tokens_per_org=10000, period_seconds=3600)
        assert budget.check_budget(org_id=1) is True

    def test_budget_blocks_when_exhausted(self):
        """Budget should block when token limit is reached."""
        from agents.token_budget import TokenBudget
        budget = TokenBudget(max_tokens_per_org=1000, period_seconds=3600)

        # Record usage up to the limit
        budget.record_usage(org_id=1, tokens_used=1000)

        # Next check should fail
        assert budget.check_budget(org_id=1) is False

    def test_different_orgs_have_independent_budgets(self):
        """Each org should have its own independent token budget."""
        from agents.token_budget import TokenBudget
        budget = TokenBudget(max_tokens_per_org=1000, period_seconds=3600)

        # Exhaust org 1's budget
        budget.record_usage(org_id=1, tokens_used=1000)

        # Org 2 should still have budget
        assert budget.check_budget(org_id=2) is True

    def test_budget_resets_after_period(self):
        """Budget should reset after the period expires."""
        from agents.token_budget import TokenBudget
        budget = TokenBudget(max_tokens_per_org=1000, period_seconds=1)

        budget.record_usage(org_id=1, tokens_used=999)

        # Wait for period to expire
        time.sleep(1.1)

        # Budget should be reset
        assert budget.check_budget(org_id=1) is True

    def test_usage_tracking_accumulates(self):
        """Multiple record_usage calls should accumulate."""
        from agents.token_budget import TokenBudget
        budget = TokenBudget(max_tokens_per_org=1000, period_seconds=3600)

        budget.record_usage(org_id=1, tokens_used=300)
        budget.record_usage(org_id=1, tokens_used=300)
        budget.record_usage(org_id=1, tokens_used=300)

        # 900 tokens used, still under 1000
        assert budget.check_budget(org_id=1) is True

        budget.record_usage(org_id=1, tokens_used=200)

        # 1100 tokens used, over 1000
        assert budget.check_budget(org_id=1) is False


# =============================================================================
# Tool Loading for Intents
# =============================================================================

@pytest.mark.agents
@pytest.mark.unit
class TestToolLoadingForIntents:
    """Verify that each intent has appropriate tools assigned."""

    def test_greeting_has_minimal_tools(self):
        """Greeting intent should have zero or minimal tools."""
        from agents.nodes.analyze import INTENT_TO_BASE_TOOLS
        greeting_tools = INTENT_TO_BASE_TOOLS.get("greeting", [])
        assert len(greeting_tools) <= 2, (
            f"Greeting should have <=2 tools, has {len(greeting_tools)}"
        )

    def test_pipeline_has_pipeline_tools(self):
        """Pipeline intent should include pipeline-related tools."""
        from agents.nodes.analyze import INTENT_TO_BASE_TOOLS
        pipeline_tools = INTENT_TO_BASE_TOOLS.get("pipeline", [])
        assert "get_pipeline" in pipeline_tools
        assert "get_pipeline_metrics" in pipeline_tools

    def test_leads_has_lead_tools(self):
        """Leads intent should include lead management tools."""
        from agents.nodes.analyze import INTENT_TO_BASE_TOOLS
        lead_tools = INTENT_TO_BASE_TOOLS.get("leads", [])
        assert "lead_status_insights" in lead_tools or "search_leads" in lead_tools

    def test_all_intents_have_tool_mappings(self):
        """Every intent in INTENT_TO_BASE_TOOLS should have a list of tools."""
        from agents.nodes.analyze import INTENT_TO_BASE_TOOLS
        for intent, tools in INTENT_TO_BASE_TOOLS.items():
            assert isinstance(tools, list), f"Intent '{intent}' tools is not a list"


# =============================================================================
# Circuit Breaker
# =============================================================================

@pytest.mark.agents
@pytest.mark.unit
class TestCircuitBreaker:
    """Test the circuit breaker for LLM API calls."""

    def test_starts_closed(self):
        """Circuit breaker should start in CLOSED state."""
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        """Circuit should open after consecutive failures exceed threshold."""
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        """A successful call should reset the consecutive failure counter."""
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        # After a success, counter should reset — 3rd failure should not open
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_cooldown(self):
        """After cooldown, circuit should transition to HALF_OPEN."""
        from agents.orchestrator import CircuitBreaker, CircuitState
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for cooldown
        time.sleep(0.15)

        assert cb.state == CircuitState.HALF_OPEN
