"""SMS Fallback Router - Mortgage CRM A+ Module #13
Route SMS through multiple providers with automatic failover.
Primary: Telnyx. Fallback: configurable secondary providers.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class ProviderRecord:
    """Tracks health and performance of a single SMS provider."""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority  # Lower = higher priority
        self.status = ProviderStatus.HEALTHY
        self.total_sent: int = 0
        self.total_failed: int = 0
        self.consecutive_failures: int = 0
        self.last_success_at: Optional[datetime] = None
        self.last_failure_at: Optional[datetime] = None
        self.last_checked_at: Optional[datetime] = None
        # Circuit-breaker thresholds
        self.failure_threshold: int = 5  # Mark degraded after N failures
        self.down_threshold: int = 10    # Mark down after N failures
        self.recovery_threshold: int = 3  # Successes needed to recover
        self._consecutive_successes: int = 0

    @property
    def error_rate(self) -> float:
        total = self.total_sent + self.total_failed
        return self.total_failed / total if total > 0 else 0.0

    def record_success(self) -> None:
        self.total_sent += 1
        self.consecutive_failures = 0
        self._consecutive_successes += 1
        self.last_success_at = datetime.now(timezone.utc)
        # Recovery logic
        if self.status != ProviderStatus.HEALTHY:
            if self._consecutive_successes >= self.recovery_threshold:
                self.status = ProviderStatus.HEALTHY
                self._consecutive_successes = 0
                logger.info(f"Provider {self.name} recovered to HEALTHY")

    def record_failure(self, error: str = "") -> None:
        self.total_failed += 1
        self.consecutive_failures += 1
        self._consecutive_successes = 0
        self.last_failure_at = datetime.now(timezone.utc)
        if self.consecutive_failures >= self.down_threshold:
            if self.status != ProviderStatus.DOWN:
                self.status = ProviderStatus.DOWN
                logger.error(f"Provider {self.name} marked DOWN after {self.consecutive_failures} failures")
        elif self.consecutive_failures >= self.failure_threshold:
            if self.status == ProviderStatus.HEALTHY:
                self.status = ProviderStatus.DEGRADED
                logger.warning(f"Provider {self.name} marked DEGRADED")


class SMSFallbackRouter:
    """
    Route outbound SMS through providers with circuit-breaker failover.

    Provider priority order (configurable):
      1. Telnyx (primary)
      2. RingCentral (fallback)
      3. Any additional provider

    Circuit breaker logic:
      - HEALTHY: normal routing
      - DEGRADED: still used but failures tracked more aggressively
      - DOWN: skipped until recovery threshold met
    """

    def __init__(self):
        self._providers: Dict[str, ProviderRecord] = {}
        self._send_functions: Dict[str, Any] = {}

    # ── Provider registration ────────────────────────────────────────────────
    def register_provider(
        self, name: str, send_fn, priority: int = 100
    ) -> None:
        """Register a provider with a send function and priority."""
        self._providers[name] = ProviderRecord(name=name, priority=priority)
        self._send_functions[name] = send_fn
        logger.info(f"Registered SMS provider: {name} (priority={priority})")

    def get_provider_health(self) -> List[Dict[str, Any]]:
        """Return health status of all providers."""
        return [
            {
                "name": p.name,
                "status": p.status.value,
                "priority": p.priority,
                "total_sent": p.total_sent,
                "total_failed": p.total_failed,
                "error_rate_pct": round(p.error_rate * 100, 1),
                "consecutive_failures": p.consecutive_failures,
                "last_success_at": p.last_success_at.isoformat() if p.last_success_at else None,
            }
            for p in sorted(self._providers.values(), key=lambda x: x.priority)
        ]

    # ── Routing ────────────────────────────────────────────────────────────────
    async def send(
        self,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        tenant_id: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send SMS through the best available provider.
        Falls back automatically if primary fails.
        """
        providers = self._get_ordered_providers(preferred_provider)

        if not providers:
            return {
                "success": False,
                "error": "No SMS providers registered",
                "provider": None,
            }

        last_error = None
        for provider_name in providers:
            provider = self._providers[provider_name]
            send_fn = self._send_functions[provider_name]

            if provider.status == ProviderStatus.DOWN:
                logger.debug(f"Skipping DOWN provider: {provider_name}")
                continue

            try:
                logger.info(f"Attempting SMS via {provider_name} to {to}")
                result = await send_fn(
                    to=to,
                    body=body,
                    from_number=from_number,
                    tenant_id=tenant_id,
                    **kwargs,
                )

                if result.get("success"):
                    provider.record_success()
                    result["provider"] = provider_name
                    return result
                else:
                    error = result.get("error", "Unknown error")
                    provider.record_failure(error)
                    last_error = error
                    logger.warning(
                        f"Provider {provider_name} failed: {error} - trying fallback"
                    )

            except Exception as e:
                provider.record_failure(str(e))
                last_error = str(e)
                logger.error(
                    f"Provider {provider_name} exception: {e} - trying fallback"
                )

        return {
            "success": False,
            "error": f"All providers failed. Last error: {last_error}",
            "provider": None,
            "providers_tried": providers,
        }

    def _get_ordered_providers(self, preferred: Optional[str] = None) -> List[str]:
        """Return providers in priority order, preferred first."""
        ordered = sorted(
            self._providers.keys(),
            key=lambda name: (
                0 if name == preferred else self._providers[name].priority
            )
        )
        return ordered

    # ── Manual override ────────────────────────────────────────────────────────
    def reset_provider(self, name: str) -> bool:
        """Manually reset a provider circuit breaker."""
        provider = self._providers.get(name)
        if provider:
            provider.status = ProviderStatus.HEALTHY
            provider.consecutive_failures = 0
            provider._consecutive_successes = 0
            logger.info(f"Provider {name} manually reset to HEALTHY")
            return True
        return False

    def force_down(self, name: str) -> bool:
        """Manually take a provider offline for maintenance."""
        provider = self._providers.get(name)
        if provider:
            provider.status = ProviderStatus.DOWN
            logger.warning(f"Provider {name} manually forced DOWN")
            return True
        return False


# ── Singleton ───────────────────────────────────────────────────────────────────
_router: Optional[SMSFallbackRouter] = None


def get_fallback_router() -> SMSFallbackRouter:
    global _router
    if _router is None:
        _router = SMSFallbackRouter()
    return _router
