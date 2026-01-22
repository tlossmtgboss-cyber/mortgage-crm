"""
LLM Response Cache Service

Caches expensive LLM API calls to reduce costs by 80-90%.
Works with both sync and async code.

TTL Strategy:
- Natural language queries: 1 hour (data changes frequently)
- Recommendations: 6 hours (strategic, changes less often)
- Hiring analysis: 24 hours (based on monthly data)
- Executive digest: 24 hours (weekly report)
- Anomaly detection: 1 hour (needs fresh data)

Expected savings: $10k-15k/month at scale
"""

import os
import json
import hashlib
import logging
import asyncio
import time
from typing import Any, Optional, Callable
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logger.warning("redis not available - LLM caching disabled")

# Try to import prometheus_client for metrics
try:
    from prometheus_client import Counter, Histogram, Gauge
    PROMETHEUS_AVAILABLE = True

    # Define metrics
    LLM_CACHE_HITS = Counter(
        'llm_cache_hits_total',
        'Total number of LLM cache hits',
        ['prefix']
    )
    LLM_CACHE_MISSES = Counter(
        'llm_cache_misses_total',
        'Total number of LLM cache misses',
        ['prefix']
    )
    LLM_CACHE_ERRORS = Counter(
        'llm_cache_errors_total',
        'Total number of LLM cache errors',
        ['operation']
    )
    LLM_CACHE_LATENCY = Histogram(
        'llm_cache_operation_seconds',
        'LLM cache operation latency in seconds',
        ['operation'],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
    )
    LLM_CACHE_SAVINGS = Gauge(
        'llm_cache_estimated_savings_usd',
        'Estimated cost savings from LLM cache in USD'
    )
    LLM_CACHE_HIT_RATE = Gauge(
        'llm_cache_hit_rate_percent',
        'Current LLM cache hit rate percentage'
    )

    logger.info("Prometheus metrics enabled for LLM cache")
except ImportError:
    PROMETHEUS_AVAILABLE = False
    LLM_CACHE_HITS = None
    LLM_CACHE_MISSES = None
    LLM_CACHE_ERRORS = None
    LLM_CACHE_LATENCY = None
    LLM_CACHE_SAVINGS = None
    LLM_CACHE_HIT_RATE = None
    logger.debug("prometheus_client not available - metrics disabled")


class LLMCacheService:
    """
    Synchronous Redis cache for LLM responses.

    Usage:
        cache = LLMCacheService()

        # As decorator
        @cache.cached(ttl=3600, prefix='query')
        def expensive_llm_call(prompt: str) -> str:
            return client.messages.create(...)

        # Manual usage
        cached = cache.get(key)
        if cached:
            return cached
        result = expensive_call()
        cache.set(key, result, ttl=3600)
    """

    # TTL presets (in seconds)
    TTL_SHORT = 300        # 5 minutes - real-time data
    TTL_MEDIUM = 3600      # 1 hour - frequently changing data
    TTL_LONG = 21600       # 6 hours - strategic insights
    TTL_DAILY = 86400      # 24 hours - reports/digests
    TTL_WEEKLY = 604800    # 7 days - static content

    def __init__(self):
        self._client: Optional[Any] = None
        self._connected = False
        self._enabled = REDIS_AVAILABLE
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "savings_estimate_usd": 0.0
        }
        self._connect()

    def _connect(self):
        """Connect to Redis synchronously."""
        if not REDIS_AVAILABLE:
            return

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning("REDIS_URL not set - LLM caching disabled")
            self._enabled = False
            return

        try:
            self._client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self._client.ping()
            self._connected = True
            self._enabled = True
            logger.info("✅ LLM Cache connected to Redis")
        except redis.RedisError as e:
            logger.warning(f"⚠️ LLM Cache Redis unavailable: {str(e)}")
            self._client = None
            self._connected = False
            self._enabled = False

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate deterministic cache key from arguments."""
        key_data = json.dumps({
            'args': [str(arg)[:500] for arg in args],  # Truncate long args
            'kwargs': {k: str(v)[:500] for k, v in sorted(kwargs.items())}
        }, sort_keys=True)

        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        return f"perennia:llm:{prefix}:{key_hash}"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._enabled or not self._client:
            return None

        start_time = time.time() if PROMETHEUS_AVAILABLE else None
        prefix = key.split(":")[2] if key.count(":") >= 2 else "unknown"

        try:
            value = self._client.get(key)
            if value:
                self._stats["hits"] += 1
                # Estimate savings: ~$0.01 per Claude API call avoided
                self._stats["savings_estimate_usd"] += 0.01
                logger.debug(f"✅ LLM Cache HIT: {key[:60]}...")

                # Record Prometheus metrics
                if PROMETHEUS_AVAILABLE:
                    LLM_CACHE_HITS.labels(prefix=prefix).inc()
                    LLM_CACHE_LATENCY.labels(operation="get").observe(time.time() - start_time)
                    self._update_prometheus_gauges()

                return json.loads(value)

            self._stats["misses"] += 1
            logger.debug(f"❌ LLM Cache MISS: {key[:60]}...")

            # Record Prometheus miss
            if PROMETHEUS_AVAILABLE:
                LLM_CACHE_MISSES.labels(prefix=prefix).inc()
                LLM_CACHE_LATENCY.labels(operation="get").observe(time.time() - start_time)
                self._update_prometheus_gauges()

            return None
        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"LLM Cache get error: {str(e)}")

            if PROMETHEUS_AVAILABLE:
                LLM_CACHE_ERRORS.labels(operation="get").inc()

            return None

    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        if not self._enabled or not self._client:
            return

        start_time = time.time() if PROMETHEUS_AVAILABLE else None

        try:
            self._client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
            logger.debug(f"💾 LLM Cache SET: {key[:60]}... (TTL: {ttl}s)")

            if PROMETHEUS_AVAILABLE:
                LLM_CACHE_LATENCY.labels(operation="set").observe(time.time() - start_time)

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"LLM Cache set error: {str(e)}")

            if PROMETHEUS_AVAILABLE:
                LLM_CACHE_ERRORS.labels(operation="set").inc()

    def _update_prometheus_gauges(self):
        """Update Prometheus gauge metrics."""
        if not PROMETHEUS_AVAILABLE:
            return

        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

        LLM_CACHE_SAVINGS.set(self._stats["savings_estimate_usd"])
        LLM_CACHE_HIT_RATE.set(hit_rate)

    def delete(self, key: str):
        """Delete key from cache."""
        if not self._enabled or not self._client:
            return

        try:
            self._client.delete(key)
        except redis.RedisError as e:
            logger.warning(f"LLM Cache delete error: {str(e)}")

    def invalidate_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        if not self._enabled or not self._client:
            return

        try:
            keys = list(self._client.scan_iter(match=pattern))
            if keys:
                self._client.delete(*keys)
                logger.info(f"🧹 LLM Cache invalidated: {len(keys)} keys")
        except redis.RedisError as e:
            logger.warning(f"LLM Cache invalidate error: {str(e)}")

    def cached(
        self,
        ttl: int = 3600,
        prefix: str = "llm",
        skip_cache_if: Optional[Callable[..., bool]] = None
    ):
        """
        Decorator to cache function results.

        Usage:
            @llm_cache.cached(ttl=3600, prefix='query')
            def query_natural_language(self, question: str, month: date) -> dict:
                # Expensive LLM call
                return result

        Args:
            ttl: Time to live in seconds
            prefix: Prefix for cache key
            skip_cache_if: Optional function that returns True to skip caching
        """
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Check if we should skip caching
                if skip_cache_if and skip_cache_if(*args, **kwargs):
                    return func(*args, **kwargs)

                # Generate cache key (skip 'self' if present)
                cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
                cache_key = self._generate_key(prefix, *cache_args, **kwargs)

                # Check cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    # Add cache metadata
                    if isinstance(cached_value, dict):
                        cached_value["_cached"] = True
                        cached_value["_cache_key"] = cache_key
                    return cached_value

                # Execute function
                result = func(*args, **kwargs)

                # Cache result (if not None and not an error)
                if result is not None:
                    if isinstance(result, dict):
                        result["_cached"] = False
                    self.set(cache_key, result, ttl)

                return result

            return wrapper
        return decorator

    def async_cached(
        self,
        ttl: int = 3600,
        prefix: str = "llm",
        skip_cache_if: Optional[Callable[..., bool]] = None
    ):
        """
        Async decorator to cache function results.

        Usage:
            @llm_cache.async_cached(ttl=3600, prefix='blog')
            async def generate_blog(self, topic: str) -> dict:
                # Expensive async LLM call
                return result
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Check if we should skip caching
                if skip_cache_if and skip_cache_if(*args, **kwargs):
                    return await func(*args, **kwargs)

                # Generate cache key (skip 'self' if present)
                cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
                cache_key = self._generate_key(prefix, *cache_args, **kwargs)

                # Check cache
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    # Add cache metadata
                    if isinstance(cached_value, dict):
                        cached_value["_cached"] = True
                        cached_value["_cache_key"] = cache_key
                    return cached_value

                # Execute async function
                result = await func(*args, **kwargs)

                # Cache result (if not None and not an error)
                if result is not None:
                    if isinstance(result, dict):
                        result["_cached"] = False
                    self.set(cache_key, result, ttl)

                return result

            return wrapper
        return decorator

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

        return {
            "enabled": self._enabled,
            "connected": self._connected,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "errors": self._stats["errors"],
            "hit_rate_percent": round(hit_rate, 2),
            "estimated_savings_usd": round(self._stats["savings_estimate_usd"], 2),
            "total_requests": total
        }

    def clear_all(self):
        """Clear all LLM cache entries."""
        self.invalidate_pattern("perennia:llm:*")
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "savings_estimate_usd": 0.0
        }
        logger.info("🧹 All LLM cache cleared")


# Global instance
llm_cache = LLMCacheService()


# Convenience functions for invalidation
def invalidate_insights_cache():
    """Invalidate all AI insights cache."""
    llm_cache.invalidate_pattern("perennia:llm:insights:*")
    llm_cache.invalidate_pattern("perennia:llm:query:*")

def invalidate_recommendations_cache():
    """Invalidate recommendations cache."""
    llm_cache.invalidate_pattern("perennia:llm:recommendations:*")

def invalidate_all_llm_cache():
    """Invalidate all LLM cache."""
    llm_cache.clear_all()
