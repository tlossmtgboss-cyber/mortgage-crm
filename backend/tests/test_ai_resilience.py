"""
Tests for AI Resilience Layer (Smart Docs)

Tests retry logic, circuit breaker, timeout handling, structured logging,
and fallback behavior for the AI resilience wrapper.
"""

import logging
import time
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

import pytest

from services.smart_docs.ai_resilience import (
    AICallConfig,
    CircuitBreaker,
    CircuitState,
    resilient_ai_call,
    get_circuit_status,
    reset_circuit,
    _is_retryable_error,
    _get_breaker,
    _breakers,
    _breakers_lock,
)


# =============================================================================
# HELPERS
# =============================================================================

@dataclass
class MockUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class MockContent:
    text: str = "mock response"


@dataclass
class MockResponse:
    content: list = None
    usage: MockUsage = None

    def __post_init__(self):
        if self.content is None:
            self.content = [MockContent()]
        if self.usage is None:
            self.usage = MockUsage()


class MockAPITimeoutError(Exception):
    """Simulates anthropic.APITimeoutError."""
    pass


class MockRateLimitError(Exception):
    """Simulates anthropic.RateLimitError."""
    pass


class MockBadRequestError(Exception):
    """Simulates anthropic.BadRequestError."""
    pass


class MockAuthenticationError(Exception):
    """Simulates anthropic.AuthenticationError."""
    pass


class MockInternalServerError(Exception):
    """Simulates anthropic.InternalServerError."""
    pass


class MockAPIStatusError(Exception):
    """Simulates anthropic.APIStatusError with a status_code."""
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"API error {status_code}")


def _make_client(side_effect=None, return_value=None):
    """Create a mock Anthropic client."""
    client = MagicMock()
    if side_effect is not None:
        client.messages.create.side_effect = side_effect
    elif return_value is not None:
        client.messages.create.return_value = return_value
    else:
        client.messages.create.return_value = MockResponse()
    return client


def _fast_config(**overrides):
    """Create a fast test config (no real sleeps)."""
    defaults = dict(
        timeout_seconds=1.0,
        max_retries=3,
        backoff_base=0.01,   # near-instant backoff for tests
        backoff_max=0.05,
        budget_per_call=0.20,
        cb_failure_threshold=5,
        cb_recovery_timeout=0.1,  # 100ms for tests
        cb_success_threshold=2,
    )
    defaults.update(overrides)
    return AICallConfig(**defaults)


@pytest.fixture(autouse=True)
def _clear_breakers():
    """Clear circuit breaker registry between tests."""
    with _breakers_lock:
        _breakers.clear()
    yield
    with _breakers_lock:
        _breakers.clear()


# =============================================================================
# RETRY TESTS
# =============================================================================

class TestRetryOnTimeout:
    def test_retries_on_timeout_then_succeeds(self):
        """Should retry on timeout errors and succeed on later attempt."""
        # Fail twice with timeout, succeed on third
        timeout_err = MockAPITimeoutError("Request timed out")
        timeout_err.__class__.__name__ = "APITimeoutError"

        client = _make_client(side_effect=[
            timeout_err,
            timeout_err,
            MockResponse(),
        ])

        config = _fast_config()
        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_timeout_retry",
            config=config,
        )

        assert result is not None
        assert client.messages.create.call_count == 3

    def test_exhausts_retries_on_persistent_timeout(self):
        """Should return None after exhausting all retry attempts."""
        timeout_err = MockAPITimeoutError("Request timed out")
        timeout_err.__class__.__name__ = "APITimeoutError"

        client = _make_client(side_effect=timeout_err)
        config = _fast_config(max_retries=3)

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_persistent_timeout",
            config=config,
        )

        assert result is None
        assert client.messages.create.call_count == 3


class TestRetryOn429:
    def test_retries_on_rate_limit_with_backoff(self):
        """Should retry on 429 rate limit errors."""
        rate_err = MockRateLimitError("Rate limited")
        rate_err.__class__.__name__ = "RateLimitError"

        client = _make_client(side_effect=[
            rate_err,
            MockResponse(),
        ])

        config = _fast_config()
        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_429_retry",
            config=config,
        )

        assert result is not None
        assert client.messages.create.call_count == 2

    def test_respects_retry_after_header(self):
        """Should respect Retry-After header from rate limit response."""
        rate_err = MockRateLimitError("Rate limited")
        rate_err.__class__.__name__ = "RateLimitError"
        # Simulate response with retry-after header
        rate_err.response = MagicMock()
        rate_err.response.headers = {"retry-after": "0.01"}

        client = _make_client(side_effect=[
            rate_err,
            MockResponse(),
        ])

        config = _fast_config()
        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_retry_after",
            config=config,
        )

        assert result is not None


class TestNoRetryOn400:
    def test_no_retry_on_bad_request(self):
        """Should NOT retry on 400 bad request errors."""
        bad_err = MockBadRequestError("Invalid request")
        bad_err.__class__.__name__ = "BadRequestError"

        client = _make_client(side_effect=bad_err)
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_no_retry_400",
            config=config,
        )

        assert result is None
        # Should have only tried once -- no retry
        assert client.messages.create.call_count == 1

    def test_no_retry_on_auth_error(self):
        """Should NOT retry on 401 authentication errors."""
        auth_err = MockAuthenticationError("Invalid API key")
        auth_err.__class__.__name__ = "AuthenticationError"

        client = _make_client(side_effect=auth_err)
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_no_retry_401",
            config=config,
        )

        assert result is None
        assert client.messages.create.call_count == 1


class TestRetryOnServerErrors:
    def test_retries_on_500(self):
        """Should retry on 500 internal server errors."""
        err = MockAPIStatusError(500)
        client = _make_client(side_effect=[err, MockResponse()])
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_retry_500",
            config=config,
        )

        assert result is not None
        assert client.messages.create.call_count == 2

    def test_retries_on_502(self):
        """Should retry on 502 bad gateway."""
        err = MockAPIStatusError(502)
        client = _make_client(side_effect=[err, MockResponse()])
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_retry_502",
            config=config,
        )

        assert result is not None

    def test_retries_on_503(self):
        """Should retry on 503 service unavailable."""
        err = MockAPIStatusError(503)
        client = _make_client(side_effect=[err, err, MockResponse()])
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_retry_503",
            config=config,
        )

        assert result is not None
        assert client.messages.create.call_count == 3


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreakerOpens:
    def test_opens_after_5_consecutive_failures(self):
        """Circuit breaker should open after cb_failure_threshold consecutive failures."""
        config = _fast_config(cb_failure_threshold=5)
        cb = CircuitBreaker("test_open", config=config)

        assert cb.state == CircuitState.CLOSED

        for i in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        """Open circuit should reject requests."""
        config = _fast_config(cb_failure_threshold=2)
        cb = CircuitBreaker("test_reject", config=config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        assert cb.allow_request() is False

    def test_resilient_call_returns_none_when_circuit_open(self):
        """resilient_ai_call should return None when circuit is open."""
        config = _fast_config(cb_failure_threshold=2, cb_recovery_timeout=9999)

        # Open the circuit by failing enough times
        err = MockAPIStatusError(503)
        client = _make_client(side_effect=err)

        # First call: exhausts retries, records failure
        resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_cb_open_fallback",
            config=config,
        )

        # Second call: exhausts retries, records another failure -> opens circuit
        resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_cb_open_fallback",
            config=config,
        )

        # Third call: circuit is open, should return None immediately
        fresh_client = _make_client()  # Would succeed if called
        result = resilient_ai_call(
            client=fresh_client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_cb_open_fallback",
            config=config,
        )

        assert result is None
        # The fresh client should NOT have been called
        assert fresh_client.messages.create.call_count == 0


class TestCircuitBreakerHalfOpens:
    def test_half_opens_after_recovery_timeout(self):
        """Circuit should transition to HALF_OPEN after recovery timeout."""
        config = _fast_config(
            cb_failure_threshold=2,
            cb_recovery_timeout=0.05,  # 50ms
        )
        cb = CircuitBreaker("test_half_open", config=config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.1)

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True


class TestCircuitBreakerCloses:
    def test_closes_after_successful_recovery(self):
        """Circuit should close after enough successes in HALF_OPEN state."""
        config = _fast_config(
            cb_failure_threshold=2,
            cb_recovery_timeout=0.05,
            cb_success_threshold=2,
        )
        cb = CircuitBreaker("test_close", config=config)

        # Open it
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for half-open
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Successful recovery
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Not closed yet

        cb.record_success()
        assert cb.state == CircuitState.CLOSED  # Now closed

    def test_reopens_on_failure_in_half_open(self):
        """Circuit should re-open on any failure in HALF_OPEN state."""
        config = _fast_config(
            cb_failure_threshold=2,
            cb_recovery_timeout=0.05,
        )
        cb = CircuitBreaker("test_reopen", config=config)

        # Open it
        cb.record_failure()
        cb.record_failure()

        # Wait for half-open
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Fail in half-open
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count_in_closed(self):
        """Success in CLOSED state should reset the failure counter."""
        config = _fast_config(cb_failure_threshold=5)
        cb = CircuitBreaker("test_reset_count", config=config)

        # Rack up some failures (but not enough to open)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Success resets
        cb.record_success()

        # These failures should start from 0 again
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Still closed (only 2 failures)


class TestCircuitBreakerReset:
    def test_manual_reset(self):
        """Manual reset should close the circuit."""
        config = _fast_config(cb_failure_threshold=2, cb_recovery_timeout=9999)
        cb = CircuitBreaker("test_manual_reset", config=config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True


# =============================================================================
# STRUCTURED LOGGING TESTS
# =============================================================================

class TestStructuredLogging:
    def test_success_log_includes_metrics(self, caplog):
        """Successful call should log operation, duration, model, tokens."""
        client = _make_client()
        config = _fast_config()

        with caplog.at_level(logging.INFO):
            result = resilient_ai_call(
                client=client,
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                operation_name="test_logging",
                org_id="org_123",
                config=config,
            )

        assert result is not None
        # Check structured log output
        log_messages = [r.message for r in caplog.records if r.levelno >= logging.INFO]
        success_logs = [m for m in log_messages if "AI call succeeded" in m]
        assert len(success_logs) == 1

        log = success_logs[0]
        assert "operation=test_logging" in log
        assert "duration_ms=" in log
        assert "model=claude-sonnet-4-20250514" in log
        assert "input_tokens=" in log
        assert "output_tokens=" in log
        assert "est_cost=" in log
        assert "org_id=org_123" in log

    def test_failure_log_includes_error_info(self, caplog):
        """Failed call should log error type and error message."""
        bad_err = MockBadRequestError("Invalid prompt")
        bad_err.__class__.__name__ = "BadRequestError"

        client = _make_client(side_effect=bad_err)
        config = _fast_config()

        with caplog.at_level(logging.WARNING):
            result = resilient_ai_call(
                client=client,
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                operation_name="test_fail_logging",
                config=config,
            )

        assert result is None
        log_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        fail_logs = [m for m in log_messages if "AI call" in m and "fail" in m.lower()]
        assert len(fail_logs) >= 1

        log = fail_logs[0]
        assert "error_type=BadRequestError" in log
        assert "operation=test_fail_logging" in log


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthCheck:
    def test_get_circuit_status_empty(self):
        """Should return empty status when no breakers exist."""
        status = get_circuit_status()
        assert status["total_services"] == 0
        assert status["circuit_breakers"] == {}

    def test_get_circuit_status_after_calls(self):
        """Should return status for each registered service."""
        config = _fast_config()
        client = _make_client()

        resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="service_a",
            config=config,
        )

        status = get_circuit_status()
        assert status["total_services"] >= 1
        assert "service_a" in status["circuit_breakers"]
        svc_status = status["circuit_breakers"]["service_a"]
        assert svc_status["state"] == "CLOSED"
        assert svc_status["total_calls"] >= 1

    def test_reset_circuit_function(self):
        """reset_circuit() should close an open breaker."""
        config = _fast_config(cb_failure_threshold=2, cb_recovery_timeout=9999)
        breaker = _get_breaker("test_reset_fn")
        breaker._config = config
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        result = reset_circuit("test_reset_fn")
        assert result is True
        assert breaker.state == CircuitState.CLOSED

    def test_reset_nonexistent_circuit(self):
        """reset_circuit() should return False for unknown service."""
        assert reset_circuit("nonexistent_service") is False


# =============================================================================
# RETRYABLE ERROR DETECTION TESTS
# =============================================================================

class TestRetryableErrorDetection:
    def test_timeout_is_retryable(self):
        err = MockAPITimeoutError("timeout")
        err.__class__.__name__ = "APITimeoutError"
        assert _is_retryable_error(err) is True

    def test_rate_limit_is_retryable(self):
        err = MockRateLimitError("rate limited")
        err.__class__.__name__ = "RateLimitError"
        assert _is_retryable_error(err) is True

    def test_internal_server_error_is_retryable(self):
        err = MockInternalServerError("server error")
        err.__class__.__name__ = "InternalServerError"
        assert _is_retryable_error(err) is True

    def test_bad_request_not_retryable(self):
        err = MockBadRequestError("bad request")
        err.__class__.__name__ = "BadRequestError"
        assert _is_retryable_error(err) is False

    def test_auth_error_not_retryable(self):
        err = MockAuthenticationError("invalid key")
        err.__class__.__name__ = "AuthenticationError"
        assert _is_retryable_error(err) is False

    def test_status_code_429_is_retryable(self):
        err = MockAPIStatusError(429)
        assert _is_retryable_error(err) is True

    def test_status_code_503_is_retryable(self):
        err = MockAPIStatusError(503)
        assert _is_retryable_error(err) is True

    def test_status_code_400_not_retryable(self):
        err = MockAPIStatusError(400)
        assert _is_retryable_error(err) is False

    def test_connection_error_is_retryable(self):
        err = Exception("Connection reset by peer")
        err.__class__.__name__ = "APIConnectionError"
        assert _is_retryable_error(err) is True


# =============================================================================
# INTEGRATION-STYLE TESTS
# =============================================================================

class TestEndToEnd:
    def test_successful_call_returns_response(self):
        """Happy path: call succeeds on first attempt."""
        client = _make_client()
        config = _fast_config()

        result = resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "hello"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_happy_path",
            config=config,
        )

        assert result is not None
        assert result.content[0].text == "mock response"
        assert client.messages.create.call_count == 1

    def test_system_prompt_passed_through(self):
        """System prompt should be forwarded to the API call."""
        client = _make_client()
        config = _fast_config()

        resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_system_prompt",
            system="You are a classifier.",
            config=config,
        )

        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a classifier."

    def test_timeout_passed_to_api(self):
        """Timeout should be forwarded to the API call."""
        client = _make_client()
        config = _fast_config()

        resilient_ai_call(
            client=client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name="test_timeout_param",
            timeout=42.0,
            config=config,
        )

        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["timeout"] == 42.0

    def test_circuit_breaker_full_lifecycle(self):
        """Test the full lifecycle: failures -> open -> half-open -> close."""
        config = _fast_config(
            max_retries=1,              # Fail fast per call
            cb_failure_threshold=3,     # Open after 3 failures
            cb_recovery_timeout=0.05,   # 50ms to half-open
            cb_success_threshold=2,     # 2 successes to close
        )

        server_err = MockAPIStatusError(503)
        fail_client = _make_client(side_effect=server_err)
        ok_client = _make_client()

        op_name = "test_lifecycle"

        # 3 failures -> opens circuit
        for _ in range(3):
            result = resilient_ai_call(
                client=fail_client,
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                operation_name=op_name,
                config=config,
            )
            assert result is None

        # Circuit is open -- should reject immediately
        result = resilient_ai_call(
            client=ok_client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name=op_name,
            config=config,
        )
        assert result is None
        assert ok_client.messages.create.call_count == 0

        # Wait for recovery
        time.sleep(0.1)

        # Half-open: first success
        result = resilient_ai_call(
            client=ok_client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name=op_name,
            config=config,
        )
        assert result is not None

        # Half-open: second success -> closes circuit
        result = resilient_ai_call(
            client=ok_client,
            messages=[{"role": "user", "content": "test"}],
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            operation_name=op_name,
            config=config,
        )
        assert result is not None

        # Verify circuit is closed
        breaker = _get_breaker(op_name)
        assert breaker.state == CircuitState.CLOSED
