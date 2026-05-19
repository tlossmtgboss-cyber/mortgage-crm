"""
Redis Cache Service
====================
Thin caching layer on top of the centralized RedisService singleton.

Provides cache_get / cache_set / cache_delete_pattern helpers that
gracefully return None / no-op when Redis is unavailable. All values
are JSON-serialized with a configurable TTL.

Usage:
    from services.cache_service import cache_get, cache_set, cache_delete_pattern

    data = cache_get("pipeline:user:42:org:7")
    if data is None:
        data = expensive_query()
        cache_set("pipeline:user:42:org:7", data, ttl=30)

    # After a mutation:
    cache_delete_pattern("pipeline:*:org:7")
"""

import json
import logging

logger = logging.getLogger(__name__)


def _get_client():
    """Return the Redis client from the centralized service, or None."""
    try:
        from services.redis_service import redis_service
        return redis_service.get_client()
    except Exception as _exc:  # noqa: BLE001
        return None


def cache_get(key: str):
    """Fetch a cached value by key. Returns deserialized Python object or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        # RedisService uses decode_responses=False, so raw is bytes
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.debug("cache_get(%s) failed: %s", key, e)
        try:
            from services.redis_service import redis_service
            redis_service.record_failure()
        except Exception as _exc:  # noqa: BLE001
            pass
        return None


def cache_set(key: str, value, ttl: int = 60):
    """Store a value in cache with TTL (seconds). No-op if Redis unavailable."""
    client = _get_client()
    if client is None:
        return
    try:
        serialized = json.dumps(value, default=str)
        client.setex(key, ttl, serialized)
    except Exception as e:
        logger.debug("cache_set(%s) failed: %s", key, e)
        try:
            from services.redis_service import redis_service
            redis_service.record_failure()
        except Exception as _exc:  # noqa: BLE001
            pass


def cache_delete_pattern(pattern: str):
    """Delete all keys matching a glob pattern. No-op if Redis unavailable.

    Uses SCAN internally (via keys()) to find matching keys, then deletes
    them in a single pipeline call. Safe for moderate key counts.
    """
    client = _get_client()
    if client is None:
        return
    try:
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
            logger.debug("cache_delete_pattern(%s): deleted %d keys", pattern, len(keys))
    except Exception as e:
        logger.debug("cache_delete_pattern(%s) failed: %s", pattern, e)
        try:
            from services.redis_service import redis_service
            redis_service.record_failure()
        except Exception as _exc:  # noqa: BLE001
            pass


def cache_delete(key: str):
    """Delete a single cache key. No-op if Redis unavailable."""
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception as e:
        logger.debug("cache_delete(%s) failed: %s", key, e)
