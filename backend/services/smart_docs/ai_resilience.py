"""
AI Resilience Layer for Smart Docs

Provides retry logic, timeouts, and circuit breaker protection for all
Anthropic API calls in the Smart Docs V2 subsystem.

Components:
    - AICallConfig: Configuration dataclass for call behavior
    - CircuitBreaker: Per-service circuit breaker (CLOSED -> OPEN -> HALF_OPEN)
    - resilient_ai_call(): Drop-in wrapper for Anthropic client.messages.create()
    - get_circuit_status(): Health-check endpoint data

Usage:
    from services.smart_docs.ai_resilience import resilient_ai_call

    response = resilient_ai_call(
        client=anthropic_client,
        messages=[{"role": "user", "content": "..."}],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        operation_name="classify_document",
        org_id=org_id,
    )
    if response is None:
        # AI call failed after all retries / circuit is open -- use fallback
        ...
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AICallConfig:
    """Configuration for resilient AI calls."""
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_max: float = 30.0
    budget_per_call: float = 0.20  # estimated max cost per call in USD

    # Circuit breaker thresholds
    cb_failure_threshold: int = 5        # consecutive failures to open circuit
    cb_recovery_timeout: float = 60.0    # seconds before half-open
    cb_success_threshold: int = 2        # successes in half-open to close


# Shared default config -- importable and overrideable
DEFAULT_CONFIG = AICallConfig()


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitState(str, Enum):
    CLOSED = "CLOSED"          # Normal operation
    OPEN = "OPEN"              # Rejecting all calls
    HALF_OPEN = "HALF_OPEN"    # Testing recovery


class CircuitBreaker:
    """
    Per-service circuit breaker.

    State machine:
        CLOSED  -- (failure_count >= threshold) --> OPEN
        OPEN    -- (recovery_timeout elapsed)   --> HALF_OPEN
        HALF_OPEN -- (success_count >= threshold) --> CLOSED
        HALF_OPEN -- (any failure)                --> OPEN
    """

    def __init__(self, service_name: str, config: Optional[AICallConfig] = None):
        self.service_name = service_name
        self._config = config or DEFAULT_CONFIG
        self._lock = threading.Lock()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._last_state_change: float = time.monotonic()
        self._total_calls = 0
        self._total_failures = 0
        self._total_rejections = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def allow_request(self) -> bool:
        """Check if the circuit allows a request through."""
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                return True
            # OPEN
            self._total_rejections += 1
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_calls += 1
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.cb_success_threshold:
                    self._transition(CircuitState.CLOSED)
                    logger.info(
                        "Circuit breaker [%s] CLOSED after %d successful recovery calls",
                        self.service_name,
                        self._success_count,
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately re-opens
                self._transition(CircuitState.OPEN)
                logger.warning(
                    "Circuit breaker [%s] re-OPENED after failure in HALF_OPEN",
                    self.service_name,
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._config.cb_failure_threshold:
                    self._transition(CircuitState.OPEN)
                    logger.error(
                        "Circuit breaker [%s] OPENED after %d consecutive failures",
                        self.service_name,
                        self._failure_count,
                    )

    def get_status(self) -> Dict[str, Any]:
        """Return circuit breaker status for health checks."""
        with self._lock:
            self._maybe_transition_to_half_open()
            now = time.monotonic()
            return {
                "service": self.service_name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_calls": self._total_calls,
                "total_failures": self._total_failures,
                "total_rejections": self._total_rejections,
                "seconds_in_state": round(now - self._last_state_change, 1),
                "seconds_since_last_failure": (
                    round(now - self._last_failure_time, 1)
                    if self._last_failure_time > 0
                    else None
                ),
            }

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED. For testing/admin."""
        with self._lock:
            self._transition(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0

    # -- internal helpers --

    def _maybe_transition_to_half_open(self) -> None:
        """Transition from OPEN -> HALF_OPEN if recovery timeout has elapsed.
        Must be called while holding self._lock.
        """
        if self._state != CircuitState.OPEN:
            return
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._config.cb_recovery_timeout:
            self._transition(CircuitState.HALF_OPEN)
            logger.info(
                "Circuit breaker [%s] HALF_OPEN after %.1fs recovery timeout",
                self.service_name,
                elapsed,
            )

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state. Must be called while holding self._lock."""
        self._state = new_state
        self._last_state_change = time.monotonic()
        if new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0


# =============================================================================
# CIRCUIT BREAKER REGISTRY (one breaker per service name)
# =============================================================================

_breakers: Dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def _get_breaker(service_name: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a given service name."""
    with _breakers_lock:
        if service_name not in _breakers:
            _breakers[service_name] = CircuitBreaker(service_name)
        return _breakers[service_name]


# =============================================================================
# RETRYABLE STATUS DETECTION
# =============================================================================

# HTTP status codes that are retryable
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 529}

# HTTP status codes that should NOT be retried (permanent errors)
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


def _is_retryable_error(error: Exception) -> bool:
    """Determine if an error is retryable."""
    error_type = type(error).__name__

    # Timeout errors are always retryable
    if "timeout" in error_type.lower() or "Timeout" in str(type(error).__mro__):
        return True

    # Check for anthropic-specific error types
    # anthropic.APITimeoutError, anthropic.APIConnectionError -> retryable
    # anthropic.RateLimitError -> retryable
    # anthropic.InternalServerError, anthropic.APIStatusError with 5xx -> retryable
    # anthropic.BadRequestError, anthropic.AuthenticationError -> not retryable
    if error_type in ("APITimeoutError", "APIConnectionError"):
        return True
    if error_type == "RateLimitError":
        return True
    if error_type in ("InternalServerError",):
        return True
    if error_type in ("BadRequestError", "AuthenticationError", "PermissionDeniedError", "NotFoundError"):
        return False

    # Check for status_code attribute (anthropic.APIStatusError subclasses)
    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        if status_code in _RETRYABLE_STATUS_CODES:
            return True
        if status_code in _NON_RETRYABLE_STATUS_CODES:
            return False

    # Connection errors are retryable
    if "connection" in error_type.lower() or "Connection" in str(error):
        return True

    # Default: not retryable (fail fast for unknown errors)
    return False


def _get_retry_after(error: Exception) -> Optional[float]:
    """Extract retry-after hint from rate limit errors, if available."""
    # anthropic.RateLimitError may have headers with Retry-After
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", {})
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass
    return None


# =============================================================================
# COST ESTIMATION
# =============================================================================

# Approximate cost per 1K tokens by model (input/output)
_MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-20250514": {"input": 0.001, "output": 0.005},
}
_DEFAULT_COST = {"input": 0.003, "output": 0.015}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost of an API call in USD."""
    costs = _MODEL_COSTS.get(model, _DEFAULT_COST)
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1000


# =============================================================================
# MAIN: resilient_ai_call
# =============================================================================

def resilient_ai_call(
    client: Any,
    messages: List[Dict],
    model: str,
    max_tokens: int,
    operation_name: str,
    timeout: Optional[float] = None,
    system: Optional[str] = None,
    org_id: Optional[Any] = None,
    config: Optional[AICallConfig] = None,
) -> Optional[Any]:
    """
    Make a resilient Anthropic API call with retry, timeout, and circuit breaker.

    Args:
        client: Anthropic client instance (must have .messages.create method)
        messages: Chat messages to send
        model: Model identifier (e.g. "claude-sonnet-4-20250514")
        max_tokens: Maximum tokens in response
        operation_name: Descriptive name for logging (e.g. "classify_document")
        timeout: Per-attempt timeout in seconds (default: config.timeout_seconds)
        system: Optional system prompt
        org_id: Optional organization ID for cost/usage tracking
        config: Optional AICallConfig override

    Returns:
        Anthropic API response object on success, or None on permanent failure.
        Callers MUST handle None gracefully (use fallback logic).
    """
    cfg = config or DEFAULT_CONFIG
    effective_timeout = timeout or cfg.timeout_seconds

    # Check circuit breaker
    breaker = _get_breaker(operation_name)
    if not breaker.allow_request():
        logger.warning(
            "Circuit breaker OPEN for '%s' -- rejecting call (org_id=%s)",
            operation_name,
            org_id,
        )
        return None

    last_error: Optional[Exception] = None

    for attempt in range(1, cfg.max_retries + 1):
        start_time = time.monotonic()
        try:
            # Build kwargs
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "timeout": effective_timeout,
            }
            if system:
                kwargs["system"] = system

            response = client.messages.create(**kwargs)

            # Success -- record metrics
            duration_ms = int((time.monotonic() - start_time) * 1000)
            input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
            output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)
            estimated_cost = _estimate_cost(model, input_tokens, output_tokens)

            logger.info(
                "AI call succeeded | operation=%s | attempt=%d/%d | "
                "duration_ms=%d | model=%s | input_tokens=%d | "
                "output_tokens=%d | est_cost=$%.4f | org_id=%s",
                operation_name,
                attempt,
                cfg.max_retries,
                duration_ms,
                model,
                input_tokens,
                output_tokens,
                estimated_cost,
                org_id,
            )

            breaker.record_success()
            return response

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            last_error = e

            logger.warning(
                "AI call failed | operation=%s | attempt=%d/%d | "
                "duration_ms=%d | error_type=%s | error=%s | org_id=%s",
                operation_name,
                attempt,
                cfg.max_retries,
                duration_ms,
                type(e).__name__,
                str(e)[:200],
                org_id,
            )

            # Check if error is retryable
            if not _is_retryable_error(e):
                logger.error(
                    "AI call non-retryable error | operation=%s | "
                    "error_type=%s | error=%s | org_id=%s",
                    operation_name,
                    type(e).__name__,
                    str(e)[:200],
                    org_id,
                )
                breaker.record_failure()
                return None

            # Don't retry on last attempt
            if attempt >= cfg.max_retries:
                break

            # Calculate backoff
            retry_after = _get_retry_after(e)
            if retry_after is not None:
                sleep_time = min(retry_after, cfg.backoff_max)
            else:
                sleep_time = min(
                    cfg.backoff_base ** (attempt - 1),
                    cfg.backoff_max,
                )

            logger.info(
                "AI call retrying | operation=%s | attempt=%d/%d | "
                "backoff_seconds=%.1f | org_id=%s",
                operation_name,
                attempt,
                cfg.max_retries,
                sleep_time,
                org_id,
            )
            time.sleep(sleep_time)

    # All retries exhausted
    breaker.record_failure()
    logger.error(
        "AI call exhausted all retries | operation=%s | "
        "max_retries=%d | last_error=%s | org_id=%s",
        operation_name,
        cfg.max_retries,
        str(last_error)[:200] if last_error else "unknown",
        org_id,
    )
    return None


# =============================================================================
# HEALTH CHECK
# =============================================================================

def get_circuit_status() -> Dict[str, Any]:
    """
    Return circuit breaker status for all registered services.

    Useful for health-check endpoints and monitoring dashboards.
    """
    with _breakers_lock:
        return {
            "circuit_breakers": {
                name: breaker.get_status()
                for name, breaker in _breakers.items()
            },
            "total_services": len(_breakers),
        }


def reset_circuit(service_name: str) -> bool:
    """
    Manually reset a circuit breaker. Returns True if the breaker existed.
    """
    with _breakers_lock:
        breaker = _breakers.get(service_name)
        if breaker:
            breaker.reset()
            logger.info("Circuit breaker [%s] manually reset to CLOSED", service_name)
            return True
        return False
