from aria.core import conversation_engine as ce


def test_get_llm_haiku_tier_returns_haiku_model():
    client = ce._get_llm("haiku")
    assert "haiku" in client.model.lower()


def test_get_llm_default_is_sonnet():
    client = ce._get_llm()
    assert "sonnet" in client.model.lower()


def test_uses_shared_circuit_breaker():
    from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker
    assert isinstance(ce._circuit_breaker, LLMCircuitBreaker)
