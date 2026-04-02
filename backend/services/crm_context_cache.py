"""
CRM Context Caching Service
Caches expensive CRMContextService calls with user-scoped keys and intent-based TTLs.

Provides 20-50x faster CRM context loading by caching the 12 database queries
that get_full_crm_context makes on every AI chat request.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)

# Try to import redis.asyncio - gracefully degrade if not available
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False
    logger.warning("redis.asyncio not available - CRM context caching disabled")


class CRMContextCache:
    """
    Specialized cache for CRM context data.

    Features:
    - User-scoped caching (each user has their own context cache)
    - Intent-based TTLs (different freshness needs per data type)
    - Graceful degradation (works without Redis)
    - Pattern-based invalidation for data changes
    """

    # TTL configuration in seconds
    TTL_CONFIG = {
        # High frequency updates - need fresh data
        "leads": 60,
        "loans": 60,
        "tasks": 60,
        "activities": 60,
        # Aggregate stats - moderate freshness
        "pipeline": 120,
        "pipeline_efficiency": 180,
        # Slower changing data
        "mum_clients": 300,
        "referral_partners": 300,
        "team_performance": 300,
        "top_referral_borrowers": 300,
        "rate_lock_intelligence": 300,
        # Historical data - very slow to change
        "loan_officer_performance": 600,
        # Full context uses shortest component TTL
        "full_context": 60,
    }

    # Key prefix for all CRM context cache entries
    KEY_PREFIX = "perennia:crm_context"

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "")
        self.redis: Optional[Any] = None
        self.enabled = False
        self._connection_lock = asyncio.Lock()
        self._stats = {"hits": 0, "misses": 0, "errors": 0}

    async def connect(self) -> bool:
        """
        Initialize Redis connection with retry logic.

        Returns:
            bool: True if connected successfully, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.info("CRM Context Cache: redis.asyncio not available")
            return False

        if not self.redis_url:
            logger.info("CRM Context Cache: REDIS_URL not set - caching disabled")
            return False

        async with self._connection_lock:
            if self.enabled:
                return True

            try:
                self.redis = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    max_connections=20,
                    retry_on_timeout=True
                )
                await self.redis.ping()
                self.enabled = True
                logger.info("CRM Context Cache connected to Redis")
                return True
            except redis.RedisError as e:
                logger.warning(f"CRM Context Cache: Redis unavailable ({e}), running uncached")
                self.enabled = False
                return False

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            try:
                await self.redis.aclose()
                logger.info("CRM Context Cache disconnected")
            except redis.RedisError as e:
                logger.warning(f"Error closing CRM Context Cache connection: {e}")
            finally:
                self.redis = None
                self.enabled = False

    def _make_key(self, user_id: int, context_type: str) -> str:
        """
        Generate cache key.
        Format: perennia:crm_context:{user_id}:{context_type}
        """
        return f"{self.KEY_PREFIX}:{user_id}:{context_type}"

    async def get_full_context(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full cached CRM context for a user.

        Args:
            user_id: User ID

        Returns:
            Cached context dict or None if not cached
        """
        if not self.enabled:
            return None

        try:
            key = self._make_key(user_id, "full_context")
            cached = await self.redis.get(key)

            if cached:
                self._stats["hits"] += 1
                data = json.loads(cached)
                logger.info(f"CRM Context CACHE HIT for user {user_id}")
                return data.get("data")

            self._stats["misses"] += 1
            logger.debug(f"CRM Context cache miss for user {user_id}")
            return None

        except redis.RedisError as e:
            self._stats["errors"] += 1
            logger.warning(f"CRM Cache get error: {e}")
            return None

    async def set_full_context(self, user_id: int, context: Dict[str, Any]):
        """
        Cache the full CRM context.

        Args:
            user_id: User ID
            context: Full CRM context dict to cache
        """
        if not self.enabled:
            return

        try:
            key = self._make_key(user_id, "full_context")
            ttl = self.TTL_CONFIG["full_context"]

            cache_data = {
                "data": context,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id
            }

            await self.redis.setex(
                key,
                ttl,
                json.dumps(cache_data, default=str)
            )
            logger.info(f"CRM Context cached for user {user_id} (TTL: {ttl}s)")

        except redis.RedisError as e:
            self._stats["errors"] += 1
            logger.warning(f"CRM Cache set error: {e}")

    # =========================================================================
    # CACHE INVALIDATION
    # =========================================================================

    async def invalidate_user_context(self, user_id: int) -> int:
        """
        Invalidate all cached context for a user.

        Args:
            user_id: User ID

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            pattern = f"{self.KEY_PREFIX}:{user_id}:*"
            deleted = 0

            async for key in self.redis.scan_iter(match=pattern):
                await self.redis.delete(key)
                deleted += 1

            if deleted > 0:
                logger.info(f"CRM Cache: Invalidated {deleted} keys for user {user_id}")
            return deleted

        except redis.RedisError as e:
            logger.warning(f"CRM Cache invalidation error: {e}")
            return 0

    async def invalidate_context_type(
        self,
        context_type: str,
        user_id: Optional[int] = None
    ) -> int:
        """
        Invalidate specific context type.

        Args:
            context_type: Type of context to invalidate (leads, loans, etc.)
            user_id: Optional - if provided, only invalidate for this user

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            deleted = 0

            if user_id:
                # Invalidate specific user's context type
                key = self._make_key(user_id, context_type)
                await self.redis.delete(key)
                # Also invalidate full context since it's now stale
                await self.redis.delete(self._make_key(user_id, "full_context"))
                deleted = 2
                logger.info(f"CRM Cache: Invalidated {context_type} for user {user_id}")
            else:
                # Invalidate this context type for ALL users
                pattern = f"{self.KEY_PREFIX}:*:{context_type}"
                async for key in self.redis.scan_iter(match=pattern):
                    await self.redis.delete(key)
                    deleted += 1

                # Also invalidate all full contexts
                pattern = f"{self.KEY_PREFIX}:*:full_context"
                async for key in self.redis.scan_iter(match=pattern):
                    await self.redis.delete(key)
                    deleted += 1

                if deleted > 0:
                    logger.info(f"CRM Cache: Invalidated {deleted} keys for context type {context_type}")

            return deleted

        except redis.RedisError as e:
            logger.warning(f"CRM Cache type invalidation error: {e}")
            return 0

    async def invalidate_all(self) -> int:
        """
        Clear all CRM context cache entries.

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            pattern = f"{self.KEY_PREFIX}:*"
            deleted = 0
            async for key in self.redis.scan_iter(match=pattern):
                await self.redis.delete(key)
                deleted += 1

            if deleted > 0:
                logger.info(f"CRM Cache: Cleared all ({deleted} keys)")
            return deleted

        except redis.RedisError as e:
            logger.warning(f"CRM Cache clear error: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats including hit rate, key count, etc.
        """
        if not self.enabled:
            return {
                "enabled": False,
                "reason": "Redis not connected",
                "redis_url_set": bool(self.redis_url)
            }

        try:
            # Count CRM context keys
            total_keys = 0
            async for _ in self.redis.scan_iter(match=f"{self.KEY_PREFIX}:*"):
                total_keys += 1

            total_ops = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_ops * 100) if total_ops > 0 else 0

            return {
                "enabled": True,
                "total_keys": total_keys,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "errors": self._stats["errors"],
                "hit_rate_percent": round(hit_rate, 2),
                "ttl_config": self.TTL_CONFIG
            }

        except Exception as e:
            return {"enabled": True, "error": "Internal server error"}


# Global instance - initialized on import, connected on startup
crm_context_cache = CRMContextCache()


# =============================================================================
# HELPER FUNCTIONS FOR CACHE INVALIDATION
# =============================================================================
# Call these from CRUD operations when data changes to keep cache fresh.
# These are fire-and-forget async functions that handle errors gracefully.

async def invalidate_on_lead_change(user_id: Optional[int] = None):
    """
    Call this when a lead is created, updated, or deleted.
    Invalidates: leads, pipeline context

    Usage in your route:
        from services.crm_context_cache import invalidate_on_lead_change
        await invalidate_on_lead_change(lead.owner_id)
    """
    try:
        await crm_context_cache.invalidate_context_type("leads", user_id)
        await crm_context_cache.invalidate_context_type("pipeline", user_id)
    except Exception as e:
        logger.warning(f"Failed to invalidate cache on lead change: {e}")


async def invalidate_on_loan_change(user_id: Optional[int] = None):
    """
    Call this when a loan is created, updated, or stage changes.
    Invalidates: loans, pipeline, mum_clients context

    Usage in your route:
        from services.crm_context_cache import invalidate_on_loan_change
        await invalidate_on_loan_change(loan.loan_officer_id)
    """
    try:
        await crm_context_cache.invalidate_context_type("loans", user_id)
        await crm_context_cache.invalidate_context_type("pipeline", user_id)
        await crm_context_cache.invalidate_context_type("mum_clients", user_id)
    except Exception as e:
        logger.warning(f"Failed to invalidate cache on loan change: {e}")


async def invalidate_on_task_change(user_id: Optional[int] = None):
    """
    Call this when a task is created, completed, or updated.
    Invalidates: tasks context

    Usage in your route:
        from services.crm_context_cache import invalidate_on_task_change
        await invalidate_on_task_change(task.owner_id)
    """
    try:
        await crm_context_cache.invalidate_context_type("tasks", user_id)
    except Exception as e:
        logger.warning(f"Failed to invalidate cache on task change: {e}")


async def invalidate_on_activity_change(user_id: Optional[int] = None):
    """
    Call this when an activity is logged.
    Invalidates: activities context

    Usage in your route:
        from services.crm_context_cache import invalidate_on_activity_change
        await invalidate_on_activity_change(activity.user_id)
    """
    try:
        await crm_context_cache.invalidate_context_type("activities", user_id)
    except Exception as e:
        logger.warning(f"Failed to invalidate cache on activity change: {e}")
