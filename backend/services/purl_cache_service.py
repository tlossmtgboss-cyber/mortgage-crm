"""
PURL Cache Service
Perennia AI - Mortgage CRM

Redis-based caching for frequently accessed PURL data.
Improves performance by reducing database queries.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from functools import wraps

try:
    import redis
except ImportError:
    redis = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# =============================================================================
# REDIS CONNECTION
# =============================================================================

_redis_client = None


def get_redis_client():
    """Get or create Redis client."""
    global _redis_client

    if _redis_client is None:
        try:
            if redis is None:
                logger.warning("Redis package not installed. Caching disabled.")
                return None
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            _redis_client.ping()
            logger.info("Redis connected successfully")
        except redis.RedisError as e:
            logger.warning(f"Redis not available: {e}. Caching disabled.")
            _redis_client = None

    return _redis_client


# =============================================================================
# CACHE SERVICE
# =============================================================================

class PURLCacheService:
    """
    Cache service for PURL system.

    Caches:
    - Workspace data
    - Token validation results
    - Application data
    - User session data
    """

    # Cache key prefixes
    PREFIX_WORKSPACE = "purl:workspace"
    PREFIX_TOKEN = "purl:token"
    PREFIX_APPLICATION = "purl:app"
    PREFIX_SESSION = "purl:session"
    PREFIX_RATE_LIMIT = "purl:rate"

    # Default TTLs (seconds)
    TTL_WORKSPACE = 300      # 5 minutes
    TTL_TOKEN = 60           # 1 minute
    TTL_APPLICATION = 120    # 2 minutes
    TTL_SESSION = 3600       # 1 hour
    TTL_RATE_LIMIT = 60      # 1 minute

    def __init__(self):
        self.redis = get_redis_client()
        self.enabled = self.redis is not None

    # =========================================================================
    # WORKSPACE CACHE
    # =========================================================================

    def cache_workspace(
        self,
        workspace_id: str,
        data: Dict[str, Any],
        ttl: int = None
    ) -> bool:
        """
        Cache workspace data.

        Args:
            workspace_id: Workspace ID
            data: Workspace data to cache
            ttl: Time to live in seconds

        Returns:
            True if cached successfully
        """
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_WORKSPACE}:{workspace_id}"
            ttl = ttl or self.TTL_WORKSPACE

            # Serialize dates
            serialized = self._serialize(data)
            self.redis.setex(key, ttl, serialized)

            logger.debug(f"Cached workspace {workspace_id} for {ttl}s")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to cache workspace: {e}")
            return False

    def get_cached_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached workspace data.

        Args:
            workspace_id: Workspace ID

        Returns:
            Cached workspace data or None
        """
        if not self.enabled:
            return None

        try:
            key = f"{self.PREFIX_WORKSPACE}:{workspace_id}"
            data = self.redis.get(key)

            if data:
                logger.debug(f"Cache hit for workspace {workspace_id}")
                return self._deserialize(data)

            logger.debug(f"Cache miss for workspace {workspace_id}")
            return None
        except redis.RedisError as e:
            logger.error(f"Failed to get cached workspace: {e}")
            return None

    def invalidate_workspace(self, workspace_id: str) -> bool:
        """
        Invalidate workspace cache.

        Args:
            workspace_id: Workspace ID

        Returns:
            True if invalidated
        """
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_WORKSPACE}:{workspace_id}"
            self.redis.delete(key)
            logger.debug(f"Invalidated cache for workspace {workspace_id}")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to invalidate workspace cache: {e}")
            return False

    # =========================================================================
    # TOKEN CACHE
    # =========================================================================

    def cache_token_validation(
        self,
        token_hash: str,
        validation_result: Dict[str, Any],
        ttl: int = None
    ) -> bool:
        """
        Cache token validation result.

        Args:
            token_hash: Hash of the token
            validation_result: Validation result data
            ttl: Time to live in seconds

        Returns:
            True if cached successfully
        """
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_TOKEN}:{token_hash}"
            ttl = ttl or self.TTL_TOKEN

            serialized = self._serialize(validation_result)
            self.redis.setex(key, ttl, serialized)

            return True
        except redis.RedisError as e:
            logger.error(f"Failed to cache token validation: {e}")
            return False

    def get_cached_token_validation(
        self,
        token_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached token validation result.

        Args:
            token_hash: Hash of the token

        Returns:
            Cached validation result or None
        """
        if not self.enabled:
            return None

        try:
            key = f"{self.PREFIX_TOKEN}:{token_hash}"
            data = self.redis.get(key)
            return self._deserialize(data) if data else None
        except redis.RedisError as e:
            logger.error(f"Failed to get cached token validation: {e}")
            return None

    def invalidate_token(self, token_hash: str) -> bool:
        """Invalidate token cache."""
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_TOKEN}:{token_hash}"
            self.redis.delete(key)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to invalidate token cache: {e}")
            return False

    # =========================================================================
    # APPLICATION CACHE
    # =========================================================================

    def cache_application(
        self,
        workspace_id: str,
        data: Dict[str, Any],
        ttl: int = None
    ) -> bool:
        """Cache application data."""
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_APPLICATION}:{workspace_id}"
            ttl = ttl or self.TTL_APPLICATION

            serialized = self._serialize(data)
            self.redis.setex(key, ttl, serialized)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to cache application: {e}")
            return False

    def get_cached_application(
        self,
        workspace_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached application data."""
        if not self.enabled:
            return None

        try:
            key = f"{self.PREFIX_APPLICATION}:{workspace_id}"
            data = self.redis.get(key)
            return self._deserialize(data) if data else None
        except redis.RedisError as e:
            logger.error(f"Failed to get cached application: {e}")
            return None

    def invalidate_application(self, workspace_id: str) -> bool:
        """Invalidate application cache."""
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_APPLICATION}:{workspace_id}"
            self.redis.delete(key)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to invalidate application cache: {e}")
            return False

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    def check_rate_limit(
        self,
        identifier: str,
        limit: int = 100,
        window: int = 60
    ) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.

        Args:
            identifier: Unique identifier (IP, token, user ID)
            limit: Maximum requests allowed
            window: Time window in seconds

        Returns:
            Tuple of (is_allowed, current_count)
        """
        if not self.enabled:
            return True, 0

        try:
            key = f"{self.PREFIX_RATE_LIMIT}:{identifier}"

            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            results = pipe.execute()

            current_count = results[0]
            is_allowed = current_count <= limit

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for {identifier}: {current_count}/{limit}")

            return is_allowed, current_count
        except redis.RedisError as e:
            logger.error(f"Rate limit check failed: {e}")
            return True, 0

    def get_rate_limit_remaining(
        self,
        identifier: str,
        limit: int = 100
    ) -> int:
        """Get remaining requests in current window."""
        if not self.enabled:
            return limit

        try:
            key = f"{self.PREFIX_RATE_LIMIT}:{identifier}"
            current = int(self.redis.get(key) or 0)
            return max(0, limit - current)
        except redis.RedisError as e:
            logger.error(f"Failed to get rate limit remaining: {e}")
            return limit

    # =========================================================================
    # SESSION CACHE
    # =========================================================================

    def set_session_data(
        self,
        session_id: str,
        data: Dict[str, Any],
        ttl: int = None
    ) -> bool:
        """Store session data."""
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_SESSION}:{session_id}"
            ttl = ttl or self.TTL_SESSION

            serialized = self._serialize(data)
            self.redis.setex(key, ttl, serialized)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to set session data: {e}")
            return False

    def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data."""
        if not self.enabled:
            return None

        try:
            key = f"{self.PREFIX_SESSION}:{session_id}"
            data = self.redis.get(key)
            return self._deserialize(data) if data else None
        except redis.RedisError as e:
            logger.error(f"Failed to get session data: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete session data."""
        if not self.enabled:
            return False

        try:
            key = f"{self.PREFIX_SESSION}:{session_id}"
            self.redis.delete(key)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to delete session: {e}")
            return False

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def invalidate_workspace_all(self, workspace_id: str) -> int:
        """
        Invalidate all cache entries for a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            # Find all related keys
            patterns = [
                f"{self.PREFIX_WORKSPACE}:{workspace_id}",
                f"{self.PREFIX_APPLICATION}:{workspace_id}",
                f"{self.PREFIX_WORKSPACE}:{workspace_id}:*",
            ]

            deleted = 0
            for pattern in patterns:
                keys = self.redis.keys(pattern)
                if keys:
                    deleted += self.redis.delete(*keys)

            logger.info(f"Invalidated {deleted} cache keys for workspace {workspace_id}")
            return deleted
        except redis.RedisError as e:
            logger.error(f"Failed to invalidate workspace cache: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.enabled:
            return {"enabled": False}

        try:
            info = self.redis.info("stats")
            memory = self.redis.info("memory")

            # Count keys by prefix
            key_counts = {}
            for prefix in [self.PREFIX_WORKSPACE, self.PREFIX_TOKEN,
                          self.PREFIX_APPLICATION, self.PREFIX_SESSION,
                          self.PREFIX_RATE_LIMIT]:
                key_counts[prefix] = len(self.redis.keys(f"{prefix}:*"))

            return {
                "enabled": True,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "memory_used": memory.get("used_memory_human", "unknown"),
                "key_counts": key_counts,
                "total_keys": sum(key_counts.values()),
            }
        except redis.RedisError as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"enabled": True, "error": "Internal server error"}

    def flush_all(self) -> bool:
        """
        Flush all PURL cache keys.

        WARNING: This will clear all cached data.
        """
        if not self.enabled:
            return False

        try:
            for prefix in [self.PREFIX_WORKSPACE, self.PREFIX_TOKEN,
                          self.PREFIX_APPLICATION, self.PREFIX_SESSION,
                          self.PREFIX_RATE_LIMIT]:
                keys = self.redis.keys(f"{prefix}:*")
                if keys:
                    self.redis.delete(*keys)

            logger.warning("Flushed all PURL cache keys")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to flush cache: {e}")
            return False

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _serialize(self, data: Any) -> str:
        """Serialize data for storage."""
        return json.dumps(data, default=str)

    def _deserialize(self, data: str) -> Any:
        """Deserialize stored data."""
        return json.loads(data)


# =============================================================================
# DECORATOR FOR CACHING
# =============================================================================

def cached(
    key_prefix: str,
    ttl: int = 300,
    key_builder: callable = None
):
    """
    Decorator for caching function results.

    Args:
        key_prefix: Cache key prefix
        ttl: Time to live in seconds
        key_builder: Function to build cache key from args/kwargs

    Example:
        @cached("workspace", ttl=300, key_builder=lambda ws_id: ws_id)
        async def get_workspace(workspace_id: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = PURLCacheService()

            if not cache.enabled:
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                cache_key = f"{key_prefix}:{hash((args, tuple(sorted(kwargs.items()))))}"

            # Try to get from cache
            cached_result = cache.redis.get(cache_key)
            if cached_result:
                return cache._deserialize(cached_result)

            # Call function and cache result
            result = await func(*args, **kwargs)

            if result is not None:
                cache.redis.setex(
                    cache_key,
                    ttl,
                    cache._serialize(result)
                )

            return result

        return wrapper
    return decorator


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

cache_service = PURLCacheService()
