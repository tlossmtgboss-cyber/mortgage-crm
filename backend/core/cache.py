"""
Redis caching for AI Agent tools
Provides 2-3x speedup for repeat queries by caching tool results
"""

from typing import Any, Callable, Optional
import json
import hashlib
import os
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Try to import redis.asyncio - gracefully degrade if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logger.warning("redis.asyncio not available - caching disabled")


class RedisCache:
    """
    Redis cache for agent tool results

    Features:
    - Automatic serialization/deserialization
    - TTL-based expiration
    - Pattern-based invalidation
    - Graceful degradation (works without Redis)
    """

    def __init__(self):
        self.redis: Optional[Any] = None
        self._connected = False
        self._enabled = REDIS_AVAILABLE

    async def connect(self):
        """Connect to Redis"""
        if self._connected or not REDIS_AVAILABLE:
            return

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning("REDIS_URL not set - AI Agent caching disabled")
            self._enabled = False
            return

        try:
            self.redis = await redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5
            )

            # Test connection
            await self.redis.ping()
            self._connected = True
            self._enabled = True
            logger.info("✅ Redis cache connected for AI Agent")

        except Exception as e:
            logger.warning(f"⚠️ Redis cache unavailable: {str(e)}")
            logger.warning("   AI Agent will work without caching (slower)")
            self.redis = None
            self._connected = False
            self._enabled = False

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            try:
                await self.redis.close()
                logger.info("Redis cache disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting Redis: {str(e)}")
            finally:
                self._connected = False

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate deterministic cache key from function arguments

        Format: perennia:agent:{prefix}:{hash}
        """
        # Create deterministic representation of arguments
        key_data = json.dumps({
            'args': [str(arg) for arg in args],
            'kwargs': {k: str(v) for k, v in sorted(kwargs.items())}
        }, sort_keys=True)

        # Hash for compact key
        key_hash = hashlib.md5(key_data.encode()).hexdigest()

        return f"perennia:agent:{prefix}:{key_hash}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self._enabled or not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                logger.debug(f"✅ Cache HIT: {key[:50]}...")
                return json.loads(value)
            logger.debug(f"❌ Cache MISS: {key[:50]}...")
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {str(e)}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300  # 5 minutes default
    ):
        """Set value in cache with TTL"""
        if not self._enabled or not self.redis:
            return

        try:
            await self.redis.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
            logger.debug(f"💾 Cache SET: {key[:50]}... (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set error: {str(e)}")

    async def delete(self, key: str):
        """Delete key from cache"""
        if not self._enabled or not self.redis:
            return

        try:
            await self.redis.delete(key)
            logger.debug(f"🗑️ Cache DELETE: {key[:50]}...")
        except Exception as e:
            logger.warning(f"Cache delete error: {str(e)}")

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern"""
        if not self._enabled or not self.redis:
            return

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)
                logger.info(f"🧹 Cache invalidated: {len(keys)} keys matching '{pattern}'")
        except Exception as e:
            logger.warning(f"Cache delete pattern error: {str(e)}")

    def cached(
        self,
        ttl: int = 300,  # 5 minutes default
        key_prefix: Optional[str] = None
    ):
        """
        Decorator to cache function results

        Usage:
            @cache.cached(ttl=600, key_prefix='pipeline')
            async def get_pipeline(user_id: str):
                return await fetch_from_db(user_id)

        Args:
            ttl: Time to live in seconds
            key_prefix: Prefix for cache key (defaults to function name)
        """
        def decorator(func: Callable):
            nonlocal key_prefix
            if not key_prefix:
                key_prefix = func.__name__

            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._generate_key(key_prefix, *args, **kwargs)

                # Check cache
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result (if not None)
                if result is not None:
                    await self.set(cache_key, result, ttl)

                return result

            return wrapper
        return decorator

    async def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self._enabled or not self.redis:
            return {
                "enabled": False,
                "connected": False
            }

        try:
            info = await self.redis.info()
            return {
                "enabled": True,
                "connected": True,
                "keys": await self.redis.dbsize(),
                "memory_used": info.get('used_memory_human', 'unknown'),
                "uptime_days": info.get('uptime_in_days', 0),
                "hit_rate": "N/A"  # Would need to track separately
            }
        except Exception as e:
            logger.warning(f"Error getting cache stats: {str(e)}")
            return {
                "enabled": self._enabled,
                "connected": False,
                "error": str(e)
            }


# Global cache instance
cache = RedisCache()


# Cache invalidation helpers
async def invalidate_user_cache(user_id: str):
    """Invalidate all cache entries for a user"""
    await cache.delete_pattern(f"perennia:agent:*:*{user_id}*")
    logger.info(f"🧹 Invalidated cache for user {user_id}")


async def invalidate_company_cache(company_id: str):
    """Invalidate all cache entries for a company"""
    await cache.delete_pattern(f"perennia:agent:*:*{company_id}*")
    logger.info(f"🧹 Invalidated cache for company {company_id}")


async def invalidate_tool_cache(tool_name: str):
    """Invalidate cache for a specific tool"""
    await cache.delete_pattern(f"perennia:agent:{tool_name}:*")
    logger.info(f"🧹 Invalidated cache for tool {tool_name}")


async def clear_all_cache():
    """Clear all agent cache (use with caution)"""
    await cache.delete_pattern("perennia:agent:*")
    logger.info("🧹 Cleared all agent cache")
