"""
Centralized Redis Client Factory & Health Check

Provides a validated, shared Redis client for the entire application:
- Token blacklist (auth/tokens.py)
- Rate limiting (middleware/rate_limiting.py)
- Caching (services/redis_cache_service.py)

On startup, validates connectivity with PING. If Redis is unavailable,
logs a warning and exposes get_redis_client() -> None so callers can
fall back to in-memory implementations.

Circuit breaker pattern: after consecutive failures, stops attempting
Redis operations for a cooldown period before retrying.
"""

import logging
import os
import threading
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class _CircuitBreaker:
    """Simple circuit breaker for Redis connections.

    States:
    - CLOSED: normal operation, all calls go through
    - OPEN: too many failures, calls are short-circuited for cooldown_seconds
    - HALF_OPEN: cooldown expired, next call is a probe

    Thread-safe via a lock on state transitions.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                    self._state = self.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        """Return True if a request should be allowed through."""
        current = self.state
        return current in (self.CLOSED, self.HALF_OPEN)

    def record_success(self):
        """Record a successful call — resets to CLOSED."""
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED

    def record_failure(self):
        """Record a failed call — may trip to OPEN."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                if self._state != self.OPEN:
                    logger.warning(
                        f"Redis circuit breaker OPEN after {self._failure_count} failures. "
                        f"Will retry in {self._cooldown_seconds}s."
                    )
                self._state = self.OPEN

    def reset(self):
        """Manually reset to CLOSED."""
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED


class RedisService:
    """Centralized Redis client with health checking and circuit breaker.

    Usage:
        from services.redis_service import redis_service

        client = redis_service.get_client()
        if client:
            client.set("key", "value")
        else:
            # Fall back to in-memory
    """

    def __init__(self):
        self._client = None
        self._connected = False
        self._redis_url: Optional[str] = None
        self._circuit_breaker = _CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
        self._lock = threading.Lock()

    def initialize(self, redis_url: Optional[str] = None) -> bool:
        """Initialize the Redis client and validate connectivity.

        Args:
            redis_url: Redis connection URL. If None, reads from REDIS_URL env var.

        Returns:
            True if Redis is connected and healthy, False otherwise.
        """
        url = redis_url or os.getenv("REDIS_URL")
        if not url:
            env = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))
            if env in ("production", "staging"):
                logger.error(
                    "REDIS_URL not set in %s — token revocation, rate limiting, "
                    "and caching will use in-memory fallbacks", env
                )
            else:
                logger.warning("REDIS_URL not set — Redis features disabled (dev mode)")
            self._connected = False
            return False

        self._redis_url = url

        try:
            import redis
            self._client = redis.from_url(
                url,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
                decode_responses=False,
            )
            # Validate with PING
            self._client.ping()
            self._connected = True
            self._circuit_breaker.reset()
            logger.info("Redis connection validated (PING OK)")
            return True
        except ImportError:
            logger.error("redis package not installed — pip install redis")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"Redis connection failed during startup: {e}")
            self._connected = False
            self._circuit_breaker.record_failure()
            return False

    def get_client(self):
        """Return the validated Redis client, or None if unavailable.

        Respects the circuit breaker: if Redis has had too many consecutive
        failures, returns None until the cooldown period expires and a probe
        succeeds.
        """
        if not self._client:
            return None

        if not self._circuit_breaker.allow_request():
            return None

        # If circuit breaker is HALF_OPEN, try a quick probe
        if self._circuit_breaker.state == _CircuitBreaker.HALF_OPEN:
            try:
                self._client.ping()
                self._circuit_breaker.record_success()
                self._connected = True
                logger.info("Redis circuit breaker recovered — connection restored")
            except Exception as e:
                self._circuit_breaker.record_failure()
                self._connected = False
                logger.warning(f"Redis probe failed during half-open: {e}")
                return None

        return self._client

    def record_failure(self):
        """Record a Redis operation failure (called by consumers on RedisError)."""
        self._circuit_breaker.record_failure()
        if self._circuit_breaker.state == _CircuitBreaker.OPEN:
            self._connected = False

    def record_success(self):
        """Record a Redis operation success (called by consumers after successful ops)."""
        self._circuit_breaker.record_success()
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def check_health(self) -> Dict[str, Any]:
        """Check Redis health for the /api/v1/health/detailed endpoint.

        Returns:
            Dict with keys: connected, latency_ms, version, circuit_breaker_state, error
        """
        result: Dict[str, Any] = {
            "connected": False,
            "latency_ms": None,
            "version": None,
            "circuit_breaker_state": self._circuit_breaker.state,
        }

        if not self._redis_url:
            result["status"] = "not_configured"
            return result

        if not self._client:
            result["status"] = "client_not_initialized"
            return result

        if not self._circuit_breaker.allow_request():
            result["status"] = "circuit_breaker_open"
            return result

        try:
            start = time.monotonic()
            self._client.ping()
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            info = self._client.info(section="server")
            version = info.get("redis_version", "unknown")
            if isinstance(version, bytes):
                version = version.decode("utf-8")

            self._circuit_breaker.record_success()
            self._connected = True

            result.update({
                "connected": True,
                "latency_ms": latency_ms,
                "version": version,
                "status": "healthy",
            })
        except Exception as e:
            self._circuit_breaker.record_failure()
            self._connected = False
            result.update({
                "status": "unhealthy",
                "error": str(e),
            })

        return result


# Module-level singleton
redis_service = RedisService()


def get_redis_client():
    """Convenience function: returns the validated Redis client or None."""
    return redis_service.get_client()


def check_redis_health() -> Dict[str, Any]:
    """Convenience function: returns Redis health status dict."""
    return redis_service.check_health()
