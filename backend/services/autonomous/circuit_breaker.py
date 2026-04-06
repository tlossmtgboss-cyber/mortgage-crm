"""
Circuit Breaker for Autonomous Agent Execution

Prevents a single org's bad data from blocking all other orgs by tracking
failures per-org per-agent and temporarily disabling execution when
failure thresholds are exceeded.

States:
    CLOSED     — Normal operation, requests pass through
    OPEN       — Failures exceeded threshold, requests blocked for cooldown
    HALF_OPEN  — After cooldown, allow one test request to probe recovery

Usage:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=3600)

    if breaker.can_execute(org_id=5, agent_type="compliance_watchdog"):
        try:
            result = await agent.run()
            breaker.record_success(5, "compliance_watchdog")
        except Exception as e:
            breaker.record_failure(5, "compliance_watchdog", str(e))
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitRecord:
    """Tracks the state of a single org+agent circuit."""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_failure_error: str = ""
    cooldown_seconds: int = 3600
    opened_at: float = 0.0
    total_failures: int = 0
    total_successes: int = 0
    total_blocked: int = 0


class CircuitBreaker:
    """Circuit breaker for autonomous agent execution.

    Thread-safe, in-memory state. No DB overhead.

    Default behavior:
        - 3 consecutive failures -> circuit opens for 1 hour
        - After cooldown, circuit moves to HALF_OPEN (1 test request allowed)
        - Success in HALF_OPEN -> CLOSED (resume normal)
        - Failure in HALF_OPEN -> re-OPEN with 2x cooldown
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: int = 3600,
        max_cooldown_seconds: int = 86400,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._default_cooldown = cooldown_seconds
        self._max_cooldown = max_cooldown_seconds
        self._circuits: Dict[str, CircuitRecord] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(org_id: int, agent_type: str) -> str:
        return f"{org_id}:{agent_type}"

    def _get_or_create(self, key: str) -> CircuitRecord:
        """Return the circuit record, creating one if it doesn't exist.
        Caller must hold self._lock.
        """
        if key not in self._circuits:
            self._circuits[key] = CircuitRecord(cooldown_seconds=self._default_cooldown)
        return self._circuits[key]

    def can_execute(self, org_id: int, agent_type: str) -> bool:
        """Check if execution is allowed for this org+agent pair."""
        key = self._key(org_id, agent_type)
        now = time.monotonic()

        with self._lock:
            circuit = self._get_or_create(key)

            if circuit.state == CircuitState.CLOSED:
                return True

            if circuit.state == CircuitState.OPEN:
                elapsed = now - circuit.opened_at
                if elapsed >= circuit.cooldown_seconds:
                    # Cooldown expired: transition to HALF_OPEN
                    circuit.state = CircuitState.HALF_OPEN
                    logger.info(
                        "Circuit %s transitioning OPEN -> HALF_OPEN after %.0fs cooldown",
                        key, elapsed,
                    )
                    return True
                # Still cooling down
                circuit.total_blocked += 1
                return False

            if circuit.state == CircuitState.HALF_OPEN:
                # Already allowed one probe; block until that probe completes
                # (record_success/failure will update state)
                circuit.total_blocked += 1
                return False

        return False  # pragma: no cover

    def record_success(self, org_id: int, agent_type: str) -> None:
        """Record successful execution. Resets failure count and closes the circuit."""
        key = self._key(org_id, agent_type)

        with self._lock:
            circuit = self._get_or_create(key)
            prev_state = circuit.state

            circuit.consecutive_failures = 0
            circuit.total_successes += 1

            if circuit.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                circuit.state = CircuitState.CLOSED
                circuit.cooldown_seconds = self._default_cooldown
                logger.info(
                    "Circuit %s %s -> CLOSED after successful execution",
                    key, prev_state.value,
                )

    def record_failure(self, org_id: int, agent_type: str, error: str) -> None:
        """Record failed execution. May trip the circuit to OPEN."""
        key = self._key(org_id, agent_type)
        now = time.monotonic()

        with self._lock:
            circuit = self._get_or_create(key)
            circuit.consecutive_failures += 1
            circuit.total_failures += 1
            circuit.last_failure_time = now
            circuit.last_failure_error = error[:500]

            if circuit.state == CircuitState.HALF_OPEN:
                # Probe failed: re-open with extended cooldown (2x, capped)
                circuit.cooldown_seconds = min(
                    circuit.cooldown_seconds * 2,
                    self._max_cooldown,
                )
                circuit.state = CircuitState.OPEN
                circuit.opened_at = now
                logger.warning(
                    "Circuit %s HALF_OPEN -> OPEN (probe failed). "
                    "Next cooldown: %ds. Error: %s",
                    key, circuit.cooldown_seconds, error[:200],
                )

            elif circuit.consecutive_failures >= self._failure_threshold:
                if circuit.state != CircuitState.OPEN:
                    circuit.state = CircuitState.OPEN
                    circuit.opened_at = now
                    logger.warning(
                        "Circuit %s CLOSED -> OPEN after %d consecutive failures. "
                        "Cooldown: %ds. Error: %s",
                        key, circuit.consecutive_failures,
                        circuit.cooldown_seconds, error[:200],
                    )

    def get_status(self) -> Dict[str, dict]:
        """Get status of all circuits for monitoring."""
        with self._lock:
            result: Dict[str, dict] = {}
            now = time.monotonic()
            for key, circuit in self._circuits.items():
                remaining = 0.0
                if circuit.state == CircuitState.OPEN:
                    elapsed = now - circuit.opened_at
                    remaining = max(0.0, circuit.cooldown_seconds - elapsed)

                result[key] = {
                    "state": circuit.state.value,
                    "consecutive_failures": circuit.consecutive_failures,
                    "last_failure_error": circuit.last_failure_error,
                    "cooldown_seconds": circuit.cooldown_seconds,
                    "cooldown_remaining_seconds": round(remaining, 1),
                    "total_failures": circuit.total_failures,
                    "total_successes": circuit.total_successes,
                    "total_blocked": circuit.total_blocked,
                }
            return result

    def get_circuit_status(self, org_id: int, agent_type: str) -> Optional[dict]:
        """Get status of a single circuit. Returns None if no record exists."""
        key = self._key(org_id, agent_type)
        with self._lock:
            if key not in self._circuits:
                return None
            circuit = self._circuits[key]
            now = time.monotonic()
            remaining = 0.0
            if circuit.state == CircuitState.OPEN:
                elapsed = now - circuit.opened_at
                remaining = max(0.0, circuit.cooldown_seconds - elapsed)
            return {
                "org_id": org_id,
                "agent_type": agent_type,
                "state": circuit.state.value,
                "consecutive_failures": circuit.consecutive_failures,
                "last_failure_error": circuit.last_failure_error,
                "cooldown_seconds": circuit.cooldown_seconds,
                "cooldown_remaining_seconds": round(remaining, 1),
                "total_failures": circuit.total_failures,
                "total_successes": circuit.total_successes,
                "total_blocked": circuit.total_blocked,
            }

    def reset(self, org_id: int, agent_type: str) -> bool:
        """Manually reset a circuit (admin action). Returns True if a circuit existed."""
        key = self._key(org_id, agent_type)
        with self._lock:
            if key not in self._circuits:
                return False
            circuit = self._circuits[key]
            prev_state = circuit.state
            circuit.state = CircuitState.CLOSED
            circuit.consecutive_failures = 0
            circuit.cooldown_seconds = self._default_cooldown
            logger.info("Circuit %s manually reset (%s -> CLOSED)", key, prev_state.value)
            return True

    def get_open_circuits(self) -> List[dict]:
        """Return only circuits in OPEN or HALF_OPEN state (for dashboards)."""
        with self._lock:
            result: List[dict] = []
            now = time.monotonic()
            for key, circuit in self._circuits.items():
                if circuit.state == CircuitState.CLOSED:
                    continue
                parts = key.split(":", 1)
                org_id = int(parts[0]) if parts[0].isdigit() else parts[0]
                agent_type = parts[1] if len(parts) > 1 else "unknown"
                remaining = 0.0
                if circuit.state == CircuitState.OPEN:
                    remaining = max(0.0, circuit.cooldown_seconds - (now - circuit.opened_at))
                result.append({
                    "org_id": org_id,
                    "agent_type": agent_type,
                    "state": circuit.state.value,
                    "consecutive_failures": circuit.consecutive_failures,
                    "last_failure_error": circuit.last_failure_error,
                    "cooldown_remaining_seconds": round(remaining, 1),
                })
            return result


# -- Module-level singleton ---------------------------------------------------

_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Return (and lazily create) the module-level circuit breaker singleton."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
