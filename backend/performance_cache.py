"""
Performance Optimization Module
In-memory caching with TTL for frequently accessed data
"""
import time
import asyncio
from typing import Any, Dict, Optional, Callable
from functools import wraps
import threading
import logging

logger = logging.getLogger(__name__)

# Thread-safe in-memory cache
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.RLock()

# Default TTL in seconds
DEFAULT_TTL = 60  # 1 minute for most data
DASHBOARD_TTL = 300  # 5 minutes for dashboards
AI_RESULT_TTL = 600  # 10 minutes for AI-generated content


def cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from prefix and arguments"""
    key_parts = [prefix]
    key_parts.extend(str(a) for a in args)
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return ":".join(key_parts)


def get_cached(key: str) -> Optional[Any]:
    """Get value from cache if not expired"""
    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if time.time() < entry["expires_at"]:
                logger.debug(f"Cache HIT: {key}")
                return entry["value"]
            else:
                # Expired, remove it
                del _cache[key]
                logger.debug(f"Cache EXPIRED: {key}")
    return None


def set_cached(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Set value in cache with TTL"""
    with _cache_lock:
        _cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time()
        }
        logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")


def invalidate_cache(prefix: str = None) -> int:
    """Invalidate cache entries matching prefix (or all if None)"""
    count = 0
    with _cache_lock:
        if prefix is None:
            count = len(_cache)
            _cache.clear()
        else:
            keys_to_delete = [k for k in _cache.keys() if k.startswith(prefix)]
            for key in keys_to_delete:
                del _cache[key]
                count += 1
    logger.info(f"Cache invalidated: {count} entries (prefix: {prefix})")
    return count


def invalidate_dashboard(user_id: int = None) -> int:
    """Invalidate dashboard cache entries. If user_id given, only that user's cache."""
    prefix = f"dashboard:{user_id}" if user_id else "dashboard"
    return invalidate_cache(prefix)


def cached(ttl: int = DEFAULT_TTL, key_prefix: str = None):
    """
    Decorator to cache function results

    Usage:
        @cached(ttl=300, key_prefix="dashboard")
        def get_dashboard_data(month):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Skip 'self' argument for methods
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            prefix = key_prefix or func.__name__
            key = cache_key(prefix, *cache_args, **kwargs)

            # Check cache
            result = get_cached(key)
            if result is not None:
                return result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result
            set_cached(key, result, ttl)
            return result
        return wrapper
    return decorator


def cached_async(ttl: int = DEFAULT_TTL, key_prefix: str = None):
    """Async version of cached decorator"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            prefix = key_prefix or func.__name__
            key = cache_key(prefix, *cache_args, **kwargs)

            result = get_cached(key)
            if result is not None:
                return result

            result = await func(*args, **kwargs)
            set_cached(key, result, ttl)
            return result
        return wrapper
    return decorator


class CacheStats:
    """Get cache statistics"""

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        with _cache_lock:
            now = time.time()
            total = len(_cache)
            expired = sum(1 for e in _cache.values() if e["expires_at"] < now)
            active = total - expired

            # Group by prefix
            prefixes = {}
            for key in _cache.keys():
                prefix = key.split(":")[0]
                prefixes[prefix] = prefixes.get(prefix, 0) + 1

            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": expired,
                "by_prefix": prefixes,
                "memory_estimate_kb": total * 2  # Rough estimate
            }


# Batch query helper for parallel execution
async def execute_parallel(*coroutines):
    """Execute multiple coroutines in parallel and return results"""
    return await asyncio.gather(*coroutines, return_exceptions=True)


def run_parallel_sync(*functions_with_args):
    """
    Run multiple sync functions in parallel using threads

    Usage:
        results = run_parallel_sync(
            (func1, (arg1, arg2)),
            (func2, (arg1,)),
            (func3, ()),
        )
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = [None] * len(functions_with_args)

    with ThreadPoolExecutor(max_workers=min(len(functions_with_args), 3)) as executor:
        future_to_idx = {}
        for idx, (func, args) in enumerate(functions_with_args):
            future = executor.submit(func, *args)
            future_to_idx[future] = idx

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error(f"Parallel execution error: {e}")
                results[idx] = {"error": "Internal server error"}

    return results
