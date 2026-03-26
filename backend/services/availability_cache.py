"""Availability Slot Cache — reduces redundant calendar queries during scheduling negotiations.

Caches available time slots per user for a configurable TTL. This prevents
repeated calendar API calls during multi-turn SMS scheduling conversations
where the prospect may take minutes between replies.
"""

import logging
import time
from typing import Optional, List, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


class AvailabilityCache:
    """In-memory cache for user availability slots with TTL expiration.

    In production, this should be backed by Redis for multi-worker consistency.
    The current in-memory implementation works for single-worker deployments
    and provides the correct interface for future Redis migration.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def _cache_key(self, user_id: int, organization_id: int, date_str: str) -> str:
        """Generate cache key scoped to tenant + user + date."""
        return f"avail:{organization_id}:{user_id}:{date_str}"

    def get_slots(
        self,
        user_id: int,
        organization_id: int,
        date_str: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached availability slots if they exist and haven't expired.

        Returns None on cache miss (caller should fetch fresh data).
        """
        key = self._cache_key(user_id, organization_id, date_str)
        entry = self._cache.get(key)

        if entry is None:
            logger.debug("Availability cache miss", extra={"cache_key": key})
            return None

        if time.time() - entry["cached_at"] > self._ttl:
            # Expired
            del self._cache[key]
            logger.debug("Availability cache expired", extra={"cache_key": key})
            return None

        logger.debug(
            "Availability cache hit",
            extra={
                "cache_key": key,
                "slot_count": len(entry["slots"]),
                "age_seconds": round(time.time() - entry["cached_at"], 1),
            },
        )
        return entry["slots"]

    def set_slots(
        self,
        user_id: int,
        organization_id: int,
        date_str: str,
        slots: List[Dict[str, Any]],
    ):
        """Cache availability slots for a user/date."""
        key = self._cache_key(user_id, organization_id, date_str)
        self._cache[key] = {
            "slots": slots,
            "cached_at": time.time(),
        }
        logger.debug(
            "Availability cached",
            extra={
                "cache_key": key,
                "slot_count": len(slots),
                "ttl_seconds": self._ttl,
            },
        )

    def invalidate(
        self,
        user_id: int,
        organization_id: int,
        date_str: Optional[str] = None,
    ):
        """Invalidate cache for a user, optionally for a specific date.

        Call this after booking an appointment to ensure stale slots
        aren't offered to the next prospect.
        """
        if date_str:
            key = self._cache_key(user_id, organization_id, date_str)
            if key in self._cache:
                del self._cache[key]
                logger.debug("Availability cache invalidated", extra={"cache_key": key})
        else:
            # Invalidate all dates for this user
            prefix = f"avail:{organization_id}:{user_id}:"
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            logger.debug(
                "Availability cache invalidated for user",
                extra={
                    "user_id": str(user_id),
                    "organization_id": str(organization_id),
                    "keys_removed": len(keys_to_delete),
                },
            )

    def clear(self):
        """Clear entire cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info("Availability cache cleared", extra={"entries_removed": count})

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        now = time.time()
        total = len(self._cache)
        expired = sum(1 for v in self._cache.values() if now - v["cached_at"] > self._ttl)
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "ttl_seconds": self._ttl,
        }


# Module-level singleton for shared access
_availability_cache: Optional[AvailabilityCache] = None


def get_availability_cache(ttl_seconds: int = AvailabilityCache.DEFAULT_TTL_SECONDS) -> AvailabilityCache:
    """Get or create the module-level availability cache singleton."""
    global _availability_cache
    if _availability_cache is None:
        _availability_cache = AvailabilityCache(ttl_seconds=ttl_seconds)
    return _availability_cache
