"""
LOS Error Handling and Circuit Breaker

Provides robust error handling for LOS API integrations:
    - Custom exception hierarchy for error classification
    - Retry logic with exponential backoff + jitter
    - Circuit breaker pattern to prevent cascading failures
    - Failure notification hooks

Enterprise Readiness: Check 7.4 (LOS Error Handling)

Usage:
    from services.los_integration.error_handler import LOSErrorHandler, LOSCircuitBreaker

    handler = LOSErrorHandler(max_retries=3)
    result = await handler.execute_with_retry(my_api_call)

    breaker = LOSCircuitBreaker(failure_threshold=5, recovery_timeout=60)
    if breaker.allow_request():
        try:
            result = await api_call()
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
"""

import asyncio
import logging
import random
import time
import threading
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Exception Hierarchy
# =============================================================================

class LOSError(Exception):
    """Base exception for LOS integration errors.

    Attributes:
        message: Human-readable error description
        code: Machine-readable error code
        retryable: Whether this error can be retried
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        code: str = "LOS_ERROR",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.retryable = retryable
        self.details = details or {}
        super().__init__(self.message)


class LOSRetryableError(LOSError):
    """Error that can be retried (rate limits, timeouts, server errors)."""

    def __init__(self, message: str, code: str = "RETRYABLE_ERROR", details: Optional[Dict] = None):
        super().__init__(message, code=code, retryable=True, details=details)


class LOSAuthError(LOSError):
    """Authentication failure."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(message, code="AUTH_FAILED", retryable=False, details=details)


class LOSRateLimitError(LOSRetryableError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        super().__init__(message, code="RATE_LIMITED")
        self.retry_after = retry_after


class LOSTimeoutError(LOSRetryableError):
    """Request timeout."""

    def __init__(self, message: str = "Request timed out"):
        super().__init__(message, code="TIMEOUT")


class LOSCircuitOpenError(LOSError):
    """Circuit breaker is open - LOS API is considered unavailable."""

    def __init__(self, recovery_at: datetime):
        self.recovery_at = recovery_at
        remaining = max(0, int((recovery_at - datetime.now(timezone.utc)).total_seconds()))
        super().__init__(
            f"LOS API circuit breaker is open. Recovery in {remaining}s.",
            code="CIRCUIT_OPEN",
            retryable=False,
        )


# =============================================================================
# Retry Handler
# =============================================================================

class LOSErrorHandler:
    """Error handler with retry logic for LOS API calls.

    Uses exponential backoff with jitter to avoid thundering herd
    when LOS API recovers from an outage.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        backoff_factor: float = 2.0,
        on_failure: Optional[Callable] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay_seconds
        self.max_delay = max_delay_seconds
        self.backoff_factor = backoff_factor
        self.on_failure = on_failure  # Callback for failure notifications

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry logic.

        Retries on LOSRetryableError with exponential backoff + jitter.
        Non-retryable errors are raised immediately.

        Args:
            func: Async callable to execute
            *args, **kwargs: Arguments to pass to func

        Returns:
            Result of func()

        Raises:
            LOSError: If all retries exhausted or non-retryable error
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)

            except LOSRetryableError as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt, e)
                    logger.warning(
                        f"LOS API retryable error (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{e.code} - {e.message}. Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LOS API max retries exceeded ({self.max_retries + 1} attempts): "
                        f"{e.code} - {e.message}"
                    )
                    if self.on_failure:
                        self._notify_failure(e, attempt + 1)

            except LOSError:
                # Non-retryable error - raise immediately
                raise

            except Exception as e:
                # Unexpected errors - classify and potentially retry
                last_error = LOSRetryableError(f"Unexpected error: {str(e)}", code="UNEXPECTED")
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Unexpected LOS error (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{type(e).__name__}: {str(e)}. Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LOS API max retries exceeded: {str(e)}")
                    if self.on_failure:
                        self._notify_failure(last_error, attempt + 1)

        raise last_error or LOSError("All retries exhausted", code="MAX_RETRIES")

    def _calculate_delay(self, attempt: int, error: Optional[LOSRetryableError] = None) -> float:
        """Calculate delay with exponential backoff + jitter.

        If the error includes a retry_after hint (from rate limiting),
        uses that instead.
        """
        if error and isinstance(error, LOSRateLimitError) and error.retry_after:
            return float(error.retry_after)

        delay = self.base_delay * (self.backoff_factor ** attempt)
        # Add jitter (0.5x to 1.5x)
        jitter = delay * (0.5 + random.random())
        return min(jitter, self.max_delay)

    def _notify_failure(self, error: LOSError, attempts: int) -> None:
        """Notify about a persistent failure."""
        try:
            if self.on_failure:
                self.on_failure({
                    "error_code": error.code,
                    "error_message": error.message,
                    "attempts": attempts,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as notify_error:
            logger.error(f"Failed to send failure notification: {notify_error}")

    @staticmethod
    def classify_http_error(status_code: int, body: str = "") -> LOSError:
        """Classify an HTTP error into the appropriate exception type.

        Args:
            status_code: HTTP status code
            body: Response body text

        Returns:
            Appropriate LOSError subclass instance
        """
        if status_code == 401:
            return LOSAuthError(f"Authentication failed: {body[:200]}")
        elif status_code == 403:
            return LOSError(f"Access forbidden: {body[:200]}", code="FORBIDDEN")
        elif status_code == 404:
            return LOSError(f"Resource not found: {body[:200]}", code="NOT_FOUND")
        elif status_code == 409:
            return LOSError(f"Conflict: {body[:200]}", code="CONFLICT")
        elif status_code == 429:
            return LOSRateLimitError(f"Rate limited: {body[:200]}")
        elif status_code >= 500:
            return LOSRetryableError(f"Server error ({status_code}): {body[:200]}", code="SERVER_ERROR")
        else:
            return LOSError(f"API error ({status_code}): {body[:200]}", code="API_ERROR")


# =============================================================================
# Circuit Breaker
# =============================================================================

class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal: all requests pass through
    OPEN = "open"            # Failing: reject requests immediately
    HALF_OPEN = "half_open"  # Testing: allow limited requests


@dataclass
class CircuitBreakerStats:
    """Statistics for the circuit breaker."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    state_history: List[Dict[str, Any]] = field(default_factory=list)


class LOSCircuitBreaker:
    """Circuit breaker for LOS API calls.

    Prevents cascading failures when the LOS API is experiencing issues.
    Tracks failure rates and temporarily stops sending requests when
    the failure threshold is exceeded.

    States:
        CLOSED  -> Normal operation; track failures
        OPEN    -> Too many failures; reject requests for recovery_timeout
        HALF_OPEN -> Recovery test; allow one request through

    Transitions:
        CLOSED -> OPEN: When consecutive_failures >= failure_threshold
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: If test request succeeds
        HALF_OPEN -> OPEN: If test request fails
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        half_open_max_requests: int = 1,
        name: str = "los_api",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.half_open_max_requests = half_open_max_requests
        self.name = name

        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._opened_at: Optional[datetime] = None
        self._half_open_requests = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, auto-transitioning OPEN -> HALF_OPEN if recovery timeout passed."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._opened_at:
                elapsed = (datetime.now(timezone.utc) - self._opened_at).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "state": self.state.value,
            "name": self.name,
            "total_requests": self._stats.total_requests,
            "successful_requests": self._stats.successful_requests,
            "failed_requests": self._stats.failed_requests,
            "rejected_requests": self._stats.rejected_requests,
            "consecutive_failures": self._stats.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
            "last_failure": self._stats.last_failure_time.isoformat() if self._stats.last_failure_time else None,
            "last_success": self._stats.last_success_time.isoformat() if self._stats.last_success_time else None,
        }

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit breaker.

        Returns:
            True if the request should proceed, False if it should be rejected
        """
        current_state = self.state

        with self._lock:
            self._stats.total_requests += 1

            if current_state == CircuitState.CLOSED:
                return True

            elif current_state == CircuitState.OPEN:
                self._stats.rejected_requests += 1
                return False

            elif current_state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                else:
                    self._stats.rejected_requests += 1
                    return False

        return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._stats.successful_requests += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.now(timezone.utc)

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
                self._half_open_requests = 0
                logger.info(f"Circuit breaker [{self.name}] CLOSED (recovery successful)")

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._stats.failed_requests += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = datetime.now(timezone.utc)

            if self._state == CircuitState.HALF_OPEN:
                # Recovery test failed - reopen
                self._transition_to(CircuitState.OPEN)
                self._half_open_requests = 0
                logger.warning(f"Circuit breaker [{self.name}] OPEN (recovery test failed)")

            elif (
                self._state == CircuitState.CLOSED
                and self._stats.consecutive_failures >= self.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)
                logger.error(
                    f"Circuit breaker [{self.name}] OPEN "
                    f"({self._stats.consecutive_failures} consecutive failures)"
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._stats.consecutive_failures = 0
            self._half_open_requests = 0
            logger.info(f"Circuit breaker [{self.name}] manually reset to CLOSED")

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state (must hold lock)."""
        old_state = self._state
        self._state = new_state
        now = datetime.now(timezone.utc)
        self._stats.last_state_change = now

        if new_state == CircuitState.OPEN:
            self._opened_at = now

        self._stats.state_history.append({
            "from": old_state.value,
            "to": new_state.value,
            "at": now.isoformat(),
        })

        # Keep history manageable
        if len(self._stats.state_history) > 50:
            self._stats.state_history = self._stats.state_history[-50:]
