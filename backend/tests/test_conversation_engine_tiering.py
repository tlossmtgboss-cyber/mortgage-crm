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


def test_llm_preserves_temperature_and_max_tokens():
    # Behavioural-equivalence guard: the ModelRouter path must keep the same
    # generation params the old _get_llm() used directly (temperature 0.3, 1024).
    client = ce._get_llm()
    assert client.temperature == 0.3
    assert client.max_tokens == 1024
