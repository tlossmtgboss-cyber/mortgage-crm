"""
Circuit Breaker for AI API

Prevents cascading failures when the AI API is having issues:
- Tracks failure rate over time
- Opens circuit after threshold exceeded
- Provides fallback responses
- Automatically attempts recovery

States:
- CLOSED: Normal operation, all requests go through
- OPEN: Failing, reject requests immediately with fallback
- HALF_OPEN: Testing recovery, allow limited requests
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing if recovered


@dataclass
class CircuitStats:
    """Statistics for circuit breaker"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: list = field(default_factory=list)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected"""
    def __init__(self, message: str, retry_after: int):
        self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for external service calls.

    Usage:
        breaker = CircuitBreaker(failure_threshold=5)

        async def call_ai():
            return await ai_client.complete(...)

        try:
            result = await breaker.call(call_ai)
        except CircuitBreakerOpenError:
            return fallback_response()
    """

    def __init__(
        self,
        name: str = "ai_api",
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            failure_threshold: Number of failures before opening circuit
            success_threshold: Successes needed in half-open to close
            timeout: Request timeout in seconds
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max concurrent calls in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._last_success_time: Optional[datetime] = None
        self._half_open_calls = 0

        self._stats = CircuitStats()
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current state, checking for automatic recovery"""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_recovery():
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to call
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result from function

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If function raises and circuit allows it through
        """
        current_state = self.state

        # Check if we should reject
        if current_state == CircuitState.OPEN:
            self._stats.rejected_requests += 1
            retry_after = self._time_until_recovery()
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN. Try again in {retry_after} seconds",
                retry_after=retry_after
            )

        # In half-open, limit concurrent calls
        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._stats.rejected_requests += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is testing recovery",
                        retry_after=5
                    )
                self._half_open_calls += 1

        self._stats.total_requests += 1

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.timeout
            )

            # Success
            self._on_success()
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Circuit breaker '{self.name}': Request timed out")
            self._on_failure()
            raise

        except Exception as e:
            logger.warning(f"Circuit breaker '{self.name}': Request failed - {e}")
            self._on_failure()
            raise

        finally:
            if current_state == CircuitState.HALF_OPEN:
                with self._lock:
                    self._half_open_calls = max(0, self._half_open_calls - 1)

    def _on_success(self):
        """Handle successful request"""
        with self._lock:
            self._stats.successful_requests += 1
            self._last_success_time = datetime.now(timezone.utc)
            self._stats.last_success_time = self._last_success_time

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Recovery successful, close circuit
                    self._transition_to(CircuitState.CLOSED)
            else:
                # Reset failure count on success in closed state
                self._failure_count = 0

    def _on_failure(self):
        """Handle failed request"""
        with self._lock:
            self._stats.failed_requests += 1
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)
            self._stats.last_failure_time = self._last_failure_time

            if self._state == CircuitState.HALF_OPEN:
                # Failure during recovery - go back to open
                self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Too many failures - open circuit
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state"""
        old_state = self._state
        self._state = new_state

        # Reset counters based on transition
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0

        # Log state change
        self._stats.state_changes.append({
            'from': old_state.value,
            'to': new_state.value,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}")

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to try recovery"""
        if not self._last_failure_time:
            return True

        time_since_failure = (
            datetime.now(timezone.utc) - self._last_failure_time
        ).total_seconds()

        return time_since_failure >= self.recovery_timeout

    def _time_until_recovery(self) -> int:
        """Calculate seconds until recovery attempt"""
        if not self._last_failure_time:
            return 0

        time_since_failure = (
            datetime.now(timezone.utc) - self._last_failure_time
        ).total_seconds()

        return max(0, self.recovery_timeout - int(time_since_failure))

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self._failure_count,
            'failure_threshold': self.failure_threshold,
            'time_until_recovery': self._time_until_recovery() if self._state == CircuitState.OPEN else None,
            'stats': {
                'total_requests': self._stats.total_requests,
                'successful': self._stats.successful_requests,
                'failed': self._stats.failed_requests,
                'rejected': self._stats.rejected_requests,
                'success_rate': round(
                    self._stats.successful_requests / max(self._stats.total_requests, 1) * 100, 2
                ),
            },
            'last_failure': self._last_failure_time.isoformat() if self._last_failure_time else None,
            'last_success': self._last_success_time.isoformat() if self._last_success_time else None,
        }

    def reset(self):
        """Manually reset circuit breaker to closed state"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset")


class AIServiceWithCircuitBreaker:
    """
    AI Service wrapper with circuit breaker protection.
    Provides fallback responses when AI is unavailable.
    """

    def __init__(self, anthropic_client, circuit_breaker: Optional[CircuitBreaker] = None):
        self.client = anthropic_client
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name="anthropic_api",
            failure_threshold=5,
            recovery_timeout=30
        )

    async def get_response(
        self,
        messages: list,
        system_prompt: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024
    ) -> str:
        """Get AI response with circuit breaker protection"""

        async def _call_ai():
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages
            )
            return response.content[0].text

        try:
            return await self.circuit_breaker.call(_call_ai)

        except CircuitBreakerOpenError as e:
            logger.warning(f"Circuit breaker open, returning fallback: {e.message}")
            return self._get_fallback_response()

        except Exception as e:
            logger.error(f"AI request failed: {e}")
            raise

    def _get_fallback_response(self) -> str:
        """Fallback response when AI is unavailable"""
        return (
            "I'm experiencing some technical difficulties at the moment. "
            "Would you like to speak directly with Tim? "
            "Click 'Call Now' below, or I can have him call you back at a convenient time."
        )

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        return self.circuit_breaker.get_status()
