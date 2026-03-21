"""
Token Budget & Rate Limiter for AI Orchestrator

Enforces per-org token budgets and per-tenant request rate limits
to prevent unbounded API costs and resource monopolization.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Token Budget
# =============================================================================

@dataclass
class OrgUsage:
    """Token usage for a single organization in the current period."""
    tokens_used: int = 0
    requests: int = 0
    period_start: float = field(default_factory=time.time)


class TokenBudget:
    """
    Per-organization token budget enforcement.

    Tracks token usage per org and blocks requests when the budget is exhausted.
    Budget resets at the start of each period (default: 1 hour).

    Usage:
        budget = TokenBudget(max_tokens_per_org=500_000, period_seconds=3600)

        if not budget.check_budget(org_id):
            return "Budget exceeded"

        # ... run LLM ...

        budget.record_usage(org_id, tokens_used=1500)
    """

    def __init__(
        self,
        max_tokens_per_org: int = 500_000,
        period_seconds: int = 3600,
    ):
        self.max_tokens_per_org = max_tokens_per_org
        self.period_seconds = period_seconds
        self._usage: Dict[int, OrgUsage] = defaultdict(OrgUsage)
        self._lock = Lock()

    def _get_or_reset(self, org_id: int) -> OrgUsage:
        """Get usage for org, resetting if period has expired."""
        usage = self._usage[org_id]
        now = time.time()
        if now - usage.period_start >= self.period_seconds:
            usage.tokens_used = 0
            usage.requests = 0
            usage.period_start = now
        return usage

    def check_budget(self, org_id: int) -> bool:
        """
        Check if an organization has remaining token budget.

        Returns True if the request should be allowed.
        """
        with self._lock:
            usage = self._get_or_reset(org_id)
            allowed = usage.tokens_used < self.max_tokens_per_org
            if not allowed:
                logger.warning(
                    f"[BUDGET] Org {org_id} exceeded token budget: "
                    f"{usage.tokens_used}/{self.max_tokens_per_org} tokens used "
                    f"in {usage.requests} requests"
                )
            return allowed

    def record_usage(self, org_id: int, tokens_used: int) -> None:
        """Record token usage for an organization."""
        with self._lock:
            usage = self._get_or_reset(org_id)
            usage.tokens_used += tokens_used
            usage.requests += 1
            logger.debug(
                f"[BUDGET] Org {org_id}: {usage.tokens_used}/{self.max_tokens_per_org} "
                f"tokens ({usage.requests} requests)"
            )

    def get_remaining(self, org_id: int) -> int:
        """Get remaining tokens for an organization."""
        with self._lock:
            usage = self._get_or_reset(org_id)
            return max(0, self.max_tokens_per_org - usage.tokens_used)

    def get_usage(self, org_id: int) -> Tuple[int, int, int]:
        """Get (tokens_used, requests, remaining) for an org."""
        with self._lock:
            usage = self._get_or_reset(org_id)
            remaining = max(0, self.max_tokens_per_org - usage.tokens_used)
            return usage.tokens_used, usage.requests, remaining


# =============================================================================
# Rate Limiter (Token Bucket Algorithm)
# =============================================================================

@dataclass
class _Bucket:
    """Token bucket state for a single tenant."""
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)


class RateLimiter:
    """
    Per-tenant rate limiter using the token bucket algorithm.

    Allows burst traffic up to `max_burst` requests, then limits
    to `requests_per_minute` sustained rate.

    Usage:
        limiter = RateLimiter(requests_per_minute=30, max_burst=10)

        allowed, retry_after = limiter.check_rate_limit(org_id)
        if not allowed:
            return f"Rate limited. Retry after {retry_after:.1f}s"
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        max_burst: int = 10,
    ):
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.max_burst = max_burst
        self._buckets: Dict[int, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=max_burst)
        )
        self._lock = Lock()

    def _refill(self, bucket: _Bucket) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_refill
        bucket.tokens = min(
            self.max_burst,
            bucket.tokens + elapsed * self.rate
        )
        bucket.last_refill = now

    def check_rate_limit(self, org_id: int) -> Tuple[bool, float]:
        """
        Check if a request is allowed under the rate limit.

        Returns:
            (allowed, retry_after_seconds)
            - allowed: True if request should proceed
            - retry_after: Seconds to wait before retrying (0 if allowed)
        """
        with self._lock:
            bucket = self._buckets[org_id]
            self._refill(bucket)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            else:
                # Calculate wait time until 1 token is available
                deficit = 1.0 - bucket.tokens
                retry_after = deficit / self.rate if self.rate > 0 else 60.0
                logger.warning(
                    f"[RATE_LIMIT] Org {org_id} rate limited. "
                    f"Retry after {retry_after:.1f}s"
                )
                return False, retry_after


# =============================================================================
# Singleton instances (configured via env vars)
# =============================================================================

import os

_token_budget: Optional[TokenBudget] = None
_rate_limiter: Optional[RateLimiter] = None


def get_token_budget() -> TokenBudget:
    """Get the singleton TokenBudget instance."""
    global _token_budget
    if _token_budget is None:
        max_tokens = int(os.getenv("AI_MAX_TOKENS_PER_ORG_HOUR", "500000"))
        period = int(os.getenv("AI_BUDGET_PERIOD_SECONDS", "3600"))
        _token_budget = TokenBudget(
            max_tokens_per_org=max_tokens,
            period_seconds=period,
        )
    return _token_budget


def get_rate_limiter() -> RateLimiter:
    """Get the singleton RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        rpm = int(os.getenv("AI_REQUESTS_PER_MINUTE", "30"))
        burst = int(os.getenv("AI_MAX_BURST", "10"))
        _rate_limiter = RateLimiter(
            requests_per_minute=rpm,
            max_burst=burst,
        )
    return _rate_limiter
