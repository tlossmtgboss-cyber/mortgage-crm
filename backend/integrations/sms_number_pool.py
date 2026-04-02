"""SMS Number Pool - Mortgage CRM A+ Module #12
Manage a pool of Telnyx phone numbers for load balancing,
per-tenant isolation, and throughput optimization.
"""
import logging
import random
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NumberStatus(str, Enum):
    ACTIVE = "active"
    COOLING_DOWN = "cooling_down"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class PooledNumber:
    """Represents a single phone number in the pool."""

    def __init__(
        self,
        phone_number: str,
        tenant_id: Optional[str] = None,
        messaging_profile_id: Optional[str] = None,
        daily_limit: int = 3000,
    ):
        self.phone_number = phone_number
        self.tenant_id = tenant_id
        self.messaging_profile_id = messaging_profile_id
        self.daily_limit = daily_limit
        self.status = NumberStatus.ACTIVE
        self.messages_sent_today: int = 0
        self.messages_sent_total: int = 0
        self.last_used_at: Optional[datetime] = None
        self.last_reset_date: Optional[str] = None  # YYYY-MM-DD
        self.error_count: int = 0
        self.consecutive_errors: int = 0
        self.added_at = datetime.now(timezone.utc)

    @property
    def daily_utilization(self) -> float:
        return self.messages_sent_today / self.daily_limit if self.daily_limit > 0 else 1.0

    @property
    def is_available(self) -> bool:
        return (
            self.status == NumberStatus.ACTIVE
            and self.messages_sent_today < self.daily_limit
        )

    def reset_daily_counters(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            self.messages_sent_today = 0
            self.last_reset_date = today

    def record_send(self, success: bool = True) -> None:
        self.messages_sent_today += 1
        self.messages_sent_total += 1
        self.last_used_at = datetime.now(timezone.utc)
        if success:
            self.consecutive_errors = 0
        else:
            self.error_count += 1
            self.consecutive_errors += 1
            if self.consecutive_errors >= 5:
                self.status = NumberStatus.COOLING_DOWN
                logger.warning(
                    f"Number {self.phone_number} suspended after {self.consecutive_errors} consecutive errors"
                )


class SMSNumberPool:
    """
    Pool of phone numbers for outbound SMS with intelligent selection:
    - Round-robin for even load distribution
    - Least-used selection for campaigns
    - Per-tenant number assignment
    - Automatic daily counter resets
    """

    def __init__(self):
        self._numbers: Dict[str, PooledNumber] = {}  # phone -> PooledNumber
        self._tenant_pools: Dict[str, List[str]] = {}  # tenant_id -> [phones]
        self._rr_index: int = 0  # Round-robin index

    # ── Number management ────────────────────────────────────────────────────
    def add_number(
        self,
        phone_number: str,
        tenant_id: Optional[str] = None,
        messaging_profile_id: Optional[str] = None,
        daily_limit: int = 3000,
    ) -> PooledNumber:
        """Add a number to the pool."""
        num = PooledNumber(
            phone_number=phone_number,
            tenant_id=tenant_id,
            messaging_profile_id=messaging_profile_id,
            daily_limit=daily_limit,
        )
        self._numbers[phone_number] = num

        if tenant_id:
            if tenant_id not in self._tenant_pools:
                self._tenant_pools[tenant_id] = []
            self._tenant_pools[tenant_id].append(phone_number)

        logger.info(f"Added number {phone_number} to pool (tenant: {tenant_id})")
        return num

    def remove_number(self, phone_number: str) -> bool:
        """Remove a number from the pool."""
        num = self._numbers.pop(phone_number, None)
        if num:
            for phones in self._tenant_pools.values():
                if phone_number in phones:
                    phones.remove(phone_number)
            return True
        return False

    def update_status(self, phone_number: str, status: NumberStatus) -> bool:
        num = self._numbers.get(phone_number)
        if num:
            num.status = status
            if status == NumberStatus.ACTIVE:
                num.consecutive_errors = 0
            logger.info(f"Number {phone_number} status -> {status}")
            return True
        return False

    # ── Number selection ─────────────────────────────────────────────────────
    def get_number(
        self,
        tenant_id: Optional[str] = None,
        strategy: str = "round_robin",
    ) -> Optional[str]:
        """
        Get the best available number.
        Strategies: round_robin, least_used, random
        """
        # Reset daily counters first
        self._reset_daily_counters()

        # Get candidates scoped to tenant or global
        candidates = self._get_available_candidates(tenant_id)
        if not candidates:
            logger.warning(f"No available numbers for tenant {tenant_id}")
            return None

        if strategy == "least_used":
            selected = min(candidates, key=lambda n: n.messages_sent_today)
        elif strategy == "random":
            selected = random.choice(candidates)
        else:  # round_robin (default)
            self._rr_index = self._rr_index % len(candidates)
            selected = candidates[self._rr_index]
            self._rr_index += 1

        return selected.phone_number

    def record_send(
        self, phone_number: str, success: bool = True
    ) -> None:
        """Record a send attempt on a specific number."""
        num = self._numbers.get(phone_number)
        if num:
            num.record_send(success)

    def _get_available_candidates(
        self, tenant_id: Optional[str] = None
    ) -> List[PooledNumber]:
        """Get all available numbers, optionally filtered by tenant."""
        if tenant_id and tenant_id in self._tenant_pools:
            phones = self._tenant_pools[tenant_id]
            return [
                self._numbers[p] for p in phones
                if p in self._numbers and self._numbers[p].is_available
            ]
        # Return all available numbers (global pool)
        return [n for n in self._numbers.values() if n.is_available]

    def _reset_daily_counters(self) -> None:
        for num in self._numbers.values():
            num.reset_daily_counters()

    # ── Pool stats ───────────────────────────────────────────────────────────────
    def get_pool_stats(self) -> Dict[str, Any]:
        """Return pool health statistics."""
        self._reset_daily_counters()
        total = len(self._numbers)
        available = sum(1 for n in self._numbers.values() if n.is_available)
        return {
            "total_numbers": total,
            "available_numbers": available,
            "cooling_down": sum(
                1 for n in self._numbers.values()
                if n.status == NumberStatus.COOLING_DOWN
            ),
            "suspended": sum(
                1 for n in self._numbers.values()
                if n.status == NumberStatus.SUSPENDED
            ),
            "messages_sent_today": sum(n.messages_sent_today for n in self._numbers.values()),
            "utilization_pct": round(
                sum(n.daily_utilization for n in self._numbers.values()) / total * 100
                if total > 0 else 0, 1
            ),
            "numbers": [
                {
                    "phone": n.phone_number,
                    "tenant_id": n.tenant_id,
                    "status": n.status.value,
                    "sent_today": n.messages_sent_today,
                    "daily_limit": n.daily_limit,
                    "utilization_pct": round(n.daily_utilization * 100, 1),
                }
                for n in self._numbers.values()
            ],
        }


# ── Singleton ───────────────────────────────────────────────────────────────────
_pool: Optional[SMSNumberPool] = None


def get_number_pool() -> SMSNumberPool:
    global _pool
    if _pool is None:
        _pool = SMSNumberPool()
    return _pool


def get_outbound_number(
    tenant_id: Optional[str] = None, strategy: str = "round_robin"
) -> Optional[str]:
    """Convenience function to get an outbound number."""
    return get_number_pool().get_number(tenant_id=tenant_id, strategy=strategy)
