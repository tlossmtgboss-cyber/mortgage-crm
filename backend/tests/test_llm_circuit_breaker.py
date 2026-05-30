import time
import pytest
from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker, CircuitState


def test_starts_closed_and_allows():
    cb = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold_failures():
    cb = LLMCircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_half_open_after_cooldown_then_closes_on_success():
    cb = LLMCircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_probe_failure_reopens():
    cb = LLMCircuitBreaker(failure_threshold=1, cooldown_seconds=0.05)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
