# utils/cache.py
import os
import redis.asyncio as redis
import json
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import logging

logger = logging.getLogger(__name__)

# Import structured cache logger
try:
    from utils.logger import cache_logger
except ImportError:
    cache_logger = None


class PerenniaCache:
    """
    Intelligent caching layer for Perennia AI responses

    Cache Strategy:
    - Pipeline queries: 5 min TTL (fast-changing data)
    - Lead status: 15 min TTL (moderate change rate)
    - Rate locks: 1 hour TTL (slower changes)
    - Performance metrics: 30 min TTL
    - General queries: 1 hour TTL
    """

    TTL_MAP = {
        "pipeline_query": 300,       # 5 minutes
        "lead_status": 900,          # 15 minutes
        "rate_lock": 3600,           # 1 hour
        "performance": 1800,         # 30 minutes
        "loan_details": 600,         # 10 minutes
        "tasks": 600,                # 10 minutes (from pattern matching)
        "sla_breach": 300,           # 5 minutes (urgent data)
        "general": 3600              # 1 hour
    }

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis: Optional[redis.Redis] = None
        self.enabled = False
        self._connection_lock = asyncio.Lock()

    async def connect(self):
        """Initialize Redis connection with retry logic"""
        async with self._connection_lock:
            if self.enabled:
                return  # Already connected

            try:
                self.redis = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    max_connections=10,  # Connection pooling
                    retry_on_timeout=True
                )

                # Test connection
                await self.redis.ping()
                self.enabled = True

                # Structured logging
                if cache_logger:
                    cache_logger.log_connection("response", "connected", self.redis_url)
                else:
                    safe_url = self.redis_url.split('@')[-1] if '@' in self.redis_url else self.redis_url
                    logger.info(f"[CACHE] Redis connected: {safe_url}")

            except Exception as e:
                if cache_logger:
                    cache_logger.log_connection("response", "failed", self.redis_url)
                    cache_logger.log_error("response", "connect", str(e))
                else:
                    logger.warning(f"[CACHE] Redis unavailable, caching disabled: {e}")
                self.enabled = False

    async def close(self):
        """Properly close Redis connection"""
        if self.redis:
            try:
                await self.redis.aclose()
                if cache_logger:
                    cache_logger.log_connection("response", "disconnected")
                else:
                    logger.info("[CACHE] Redis connection closed")
            except Exception as e:
                logger.warning(f"[CACHE] Error closing Redis: {e}")
            finally:
                self.redis = None
                self.enabled = False

    def _get_cache_key(
        self,
        query: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """
        Generate cache key with tenant + user isolation (ISO-014).
        Format: perennia:{org_id}:query:{user_id}:{query_hash}

        Tenant prefix ensures one org's cache never collides with another's.
        """
        query_normalized = query.lower().strip()
        query_hash = hashlib.sha256(query_normalized.encode()).hexdigest()[:16]

        tenant = f"org:{org_id}" if org_id else "global"
        user = user_id or "anon"
        return f"perennia:{tenant}:query:{user}:{query_hash}"

    async def get(self, query: str, user_id: Optional[str] = None, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get cached response if available. org_id ensures tenant isolation (ISO-014)."""
        if not self.enabled:
            return None

        try:
            cache_key = self._get_cache_key(query, user_id, org_id)
            cached = await self.redis.get(cache_key)

            if cached:
                data = json.loads(cached)

                # Validate cache isn't corrupted
                if not isinstance(data, dict) or "response" not in data:
                    logger.warning(f"[CACHE] Corrupted cache entry, deleting: {cache_key}")
                    await self.redis.delete(cache_key)
                    return None

                # Get TTL remaining
                ttl_remaining = await self.redis.ttl(cache_key)

                # Structured logging
                if cache_logger:
                    cache_logger.log_hit("response", query, ttl_remaining=ttl_remaining, user_id=user_id)
                else:
                    logger.info(f"[CACHE HIT] Query: {query[:50]}... (TTL: {ttl_remaining}s)")

                # Add cache metadata
                data["cached"] = True
                data["cache_key"] = cache_key
                data["ttl_remaining"] = ttl_remaining

                return data

            # Structured logging for miss
            if cache_logger:
                cache_logger.log_miss("response", query, user_id=user_id)
            else:
                logger.debug(f"[CACHE MISS] Query: {query[:50]}...")
            return None

        except json.JSONDecodeError as e:
            if cache_logger:
                cache_logger.log_error("response", "get", str(e), query)
            else:
                logger.warning(f"[CACHE ERROR] Invalid JSON in cache: {e}")
            return None
        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "get", str(e), query)
            else:
                logger.warning(f"[CACHE ERROR] Get failed: {e}")
            return None

    async def set(
        self,
        query: str,
        response: Dict[str, Any],
        intent: str = "general",
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ):
        """Cache response with intent-based TTL. org_id ensures tenant isolation (ISO-014)."""
        if not self.enabled:
            return

        try:
            cache_key = self._get_cache_key(query, user_id, org_id)
            ttl = self.TTL_MAP.get(intent, 3600)

            # Add cache metadata
            cache_data = {
                **response,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "intent": intent,
                "ttl": ttl,
                "query": query  # Store original query for debugging
            }

            # Remove any existing large objects that shouldn't be cached
            if "metadata" in cache_data and isinstance(cache_data["metadata"], dict):
                # Don't cache raw tool results, only final response
                cache_data["metadata"] = {
                    k: v for k, v in cache_data["metadata"].items()
                    if k.endswith("_duration")  # Keep timing info only
                }

            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(cache_data, default=str)  # Handle non-serializable objects
            )

            # Structured logging
            if cache_logger:
                cache_logger.log_set("response", query, intent, ttl, user_id=user_id)
            else:
                logger.debug(f"[CACHE SET] Cached for {ttl}s (intent: {intent})")

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "set", str(e), query)
            else:
                logger.warning(f"[CACHE ERROR] Set failed: {e}")

    async def invalidate(self, query: str, user_id: Optional[str] = None, org_id: Optional[str] = None):
        """Invalidate a specific cached query"""
        if not self.enabled:
            return

        try:
            cache_key = self._get_cache_key(query, user_id, org_id)
            deleted = await self.redis.delete(cache_key)

            if deleted:
                if cache_logger:
                    cache_logger.log_invalidation("response", "specific_query", 1)
                else:
                    logger.info(f"[CACHE] Invalidated: {cache_key}")

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "invalidate", str(e), query)
            else:
                logger.warning(f"[CACHE ERROR] Invalidate failed: {e}")

    async def invalidate_tenant(self, org_id: str) -> int:
        """Invalidate ALL cache entries for a specific tenant (ISO-015).

        This ensures one tenant's cache flush does not affect other tenants.
        """
        if not self.enabled:
            return 0

        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=f"perennia:org:{org_id}:*",
                    count=100
                )

                if keys:
                    deleted += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            if cache_logger:
                cache_logger.log_invalidation("response", f"tenant:{org_id}", deleted)
            else:
                logger.info(f"[CACHE] Invalidated {deleted} keys for tenant org_id={org_id}")
            return deleted

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "invalidate_tenant", str(e))
            else:
                logger.warning(f"[CACHE ERROR] Tenant invalidation failed: {e}")
            return 0

    async def invalidate_pattern(self, pattern: str):
        """
        Invalidate cache entries matching a pattern

        Example: invalidate_pattern("lead_123") invalidates all queries about lead 123
        """
        if not self.enabled:
            return 0

        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match="perennia:query:*",
                    count=100
                )

                if keys:
                    # Filter keys by pattern in the query part
                    matching_keys = []
                    for key in keys:
                        cached_data = await self.redis.get(key)
                        if cached_data:
                            try:
                                data = json.loads(cached_data)
                                if pattern.lower() in data.get("query", "").lower():
                                    matching_keys.append(key)
                            except Exception as e:
                                logger.exception(f"Failed to parse cached data for pattern matching: {e}")
                                continue

                    if matching_keys:
                        deleted += await self.redis.delete(*matching_keys)

                if cursor == 0:
                    break

            # Structured logging
            if cache_logger:
                cache_logger.log_invalidation("response", "pattern_match", deleted, pattern=pattern)
            else:
                logger.info(f"[CACHE] Invalidated {deleted} keys matching '{pattern}'")
            return deleted

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "invalidate_pattern", str(e))
            else:
                logger.warning(f"[CACHE ERROR] Invalidate pattern failed: {e}")
            return 0

    async def invalidate_by_intent(self, intent: str):
        """Invalidate all cached queries for a specific intent"""
        if not self.enabled:
            return 0

        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match="perennia:query:*",
                    count=100
                )

                if keys:
                    matching_keys = []
                    for key in keys:
                        cached_data = await self.redis.get(key)
                        if cached_data:
                            try:
                                data = json.loads(cached_data)
                                if data.get("intent") == intent:
                                    matching_keys.append(key)
                            except Exception as e:
                                logger.exception(f"Failed to parse cached data for intent matching: {e}")
                                continue

                    if matching_keys:
                        deleted += await self.redis.delete(*matching_keys)

                if cursor == 0:
                    break

            # Structured logging
            if cache_logger:
                cache_logger.log_invalidation("response", f"intent:{intent}", deleted)
            else:
                logger.info(f"[CACHE] Invalidated {deleted} keys for intent '{intent}'")
            return deleted

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "invalidate_by_intent", str(e))
            else:
                logger.warning(f"[CACHE ERROR] Invalidate by intent failed: {e}")
            return 0

    async def clear_all(self):
        """Clear all Perennia cache entries (use with caution)"""
        if not self.enabled:
            return 0

        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match="perennia:query:*",
                    count=100
                )

                if keys:
                    deleted += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            # Structured logging
            if cache_logger:
                cache_logger.log_invalidation("response", "clear_all", deleted)
            else:
                logger.info(f"[CACHE] Cleared all cache ({deleted} keys)")
            return deleted

        except Exception as e:
            if cache_logger:
                cache_logger.log_error("response", "clear_all", str(e))
            else:
                logger.warning(f"[CACHE ERROR] Clear all failed: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False, "reason": "Redis not connected"}

        try:
            # Get Redis info
            info = await self.redis.info("stats")

            # Count Perennia-specific keys
            cursor = 0
            total_keys = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match="perennia:query:*",
                    count=100
                )
                total_keys += len(keys)

                if cursor == 0:
                    break

            total_ops = info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)
            hit_rate = info.get("keyspace_hits", 0) / total_ops if total_ops > 0 else 0

            return {
                "enabled": True,
                "total_keys": total_keys,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": round(hit_rate * 100, 2),
                "memory_used": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0)
            }

        except Exception as e:
            return {"enabled": True, "error": "Internal server error"}


# Global cache instance
cache = PerenniaCache()
