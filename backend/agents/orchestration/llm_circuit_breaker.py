"""
Shared LLM circuit breaker.

Single source of truth, extracted from agents/orchestrator.py (CircuitBreaker)
and aria/core/conversation_engine.py (_AriaCircuitBreaker), which were identical.
Thread-safe; fast-fails LLM calls during Anthropic outages.
"""
import logging
import threading
import time as _time_module
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LLMCircuitBreaker:
    """Thread-safe circuit breaker for LLM API calls."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0, name: str = "llm"):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = _time_module.monotonic() - self._last_failure_time
                if elapsed >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning("[CIRCUIT-BREAKER:%s] OPEN -> HALF_OPEN (cooldown %.1fs elapsed)",
                                   self.name, self.cooldown_seconds)
            return self._state

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        with self._lock:
            prev = self._state
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            if prev != CircuitState.CLOSED:
                logger.warning("[CIRCUIT-BREAKER:%s] %s -> CLOSED (success)", self.name, prev.value)

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = _time_module.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("[CIRCUIT-BREAKER:%s] HALF_OPEN -> OPEN (probe failed)", self.name)
            elif (self._state == CircuitState.CLOSED
                  and self._consecutive_failures >= self.failure_threshold):
                self._state = CircuitState.OPEN
                logger.warning("[CIRCUIT-BREAKER:%s] CLOSED -> OPEN (%d consecutive failures)",
                               self.name, self._consecutive_failures)
