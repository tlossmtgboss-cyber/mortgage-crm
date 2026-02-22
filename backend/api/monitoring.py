# backend/api/monitoring.py
"""
Monitoring endpoints for cache health and performance metrics.
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/cache/health")
async def cache_health():
    """
    Check health of both cache layers.

    Returns status of:
    - Response cache (AI query responses)
    - Tool cache (individual tool results)
    """
    response_stats = {"enabled": False}
    tool_stats = {"enabled": False}

    try:
        from utils.cache import cache as response_cache
        response_stats = await response_cache.get_stats()
    except ImportError:
        response_stats = {"enabled": False, "error": "Module not available"}
    except Exception as e:
        response_stats = {"enabled": False, "error": "Internal server error"}

    try:
        from core.cache import cache as tool_cache
        tool_stats = await tool_cache.get_stats()
    except ImportError:
        tool_stats = {"enabled": False, "error": "Module not available"}
    except Exception as e:
        tool_stats = {"enabled": False, "error": "Internal server error"}

    response_enabled = response_stats.get("enabled", False)
    tool_enabled = tool_stats.get("enabled", False) or tool_stats.get("connected", False)

    return {
        "response_cache": {
            "enabled": response_enabled,
            "hit_rate": response_stats.get("hit_rate", 0),
            "total_keys": response_stats.get("total_keys", 0),
            "hits": response_stats.get("hits", 0),
            "misses": response_stats.get("misses", 0),
            "memory_used": response_stats.get("memory_used", "unknown")
        },
        "tool_cache": {
            "enabled": tool_enabled,
            "connected": tool_stats.get("connected", False),
            "total_keys": tool_stats.get("keys", 0),
            "memory_used": tool_stats.get("memory_used", "unknown")
        },
        "overall_health": response_enabled or tool_enabled,
        "status": "healthy" if (response_enabled or tool_enabled) else "degraded"
    }


@router.get("/cache/performance")
async def cache_performance():
    """
    Calculate performance improvements from caching.

    Returns estimated time savings and speedup metrics.
    """
    try:
        from utils.cache import cache as response_cache
        response_stats = await response_cache.get_stats()
    except Exception as e:
        return {
            "error": "Internal server error",
            "message": "Could not retrieve cache stats"
        }

    # Get hit/miss counts
    cache_hits = response_stats.get("hits", 0)
    cache_misses = response_stats.get("misses", 0)
    total_requests = cache_hits + cache_misses

    # Performance assumptions (based on typical response times)
    AVG_FRESH_TIME = 10.0   # 10 seconds for uncached AI query
    AVG_CACHED_TIME = 0.2   # 200ms for cached response

    # Calculate time savings
    time_saved = cache_hits * (AVG_FRESH_TIME - AVG_CACHED_TIME)

    # Calculate effective average response time
    if total_requests > 0:
        effective_avg = (
            (cache_hits * AVG_CACHED_TIME + cache_misses * AVG_FRESH_TIME)
            / total_requests
        )
        speedup_factor = AVG_FRESH_TIME / effective_avg if effective_avg > 0 else 1
    else:
        effective_avg = 0
        speedup_factor = 1

    return {
        "total_requests": total_requests,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "hit_rate_percent": response_stats.get("hit_rate", 0),
        "performance": {
            "time_saved_seconds": round(time_saved, 2),
            "time_saved_minutes": round(time_saved / 60, 2),
            "time_saved_hours": round(time_saved / 3600, 2),
            "effective_avg_response_time": round(effective_avg, 2),
            "speedup_factor": round(speedup_factor, 2)
        },
        "assumptions": {
            "avg_fresh_response_time": AVG_FRESH_TIME,
            "avg_cached_response_time": AVG_CACHED_TIME
        }
    }


@router.get("/cache/keys")
async def cache_keys_summary():
    """
    Get summary of cached keys by intent/type.

    Useful for understanding what's being cached.
    """
    try:
        from utils.cache import cache as response_cache

        if not response_cache.enabled:
            return {"enabled": False, "message": "Cache not connected"}

        # Scan keys and categorize by intent
        intent_counts = {}
        user_counts = {}
        total_keys = 0

        cursor = 0
        while True:
            cursor, keys = await response_cache.redis.scan(
                cursor,
                match="perennia:query:*",
                count=100
            )

            for key in keys:
                total_keys += 1

                # Extract user_id from key
                parts = key.split(":")
                if len(parts) >= 3:
                    user_part = parts[2]
                    user_counts[user_part] = user_counts.get(user_part, 0) + 1

                # Get intent from cached data
                try:
                    cached_data = await response_cache.redis.get(key)
                    if cached_data:
                        import json
                        data = json.loads(cached_data)
                        intent = data.get("intent", "unknown")
                        intent_counts[intent] = intent_counts.get(intent, 0) + 1
                except Exception as e:
                    logger.exception(f"Failed to parse cached intent data: {e}")
                    intent_counts["parse_error"] = intent_counts.get("parse_error", 0) + 1

            if cursor == 0:
                break

        return {
            "total_keys": total_keys,
            "by_intent": dict(sorted(intent_counts.items(), key=lambda x: -x[1])),
            "by_user": {
                "total_users": len(user_counts),
                "global_keys": user_counts.get("global", 0),
                "user_specific_keys": total_keys - user_counts.get("global", 0)
            }
        }

    except Exception as e:
        logger.error(f"Error getting cache keys summary: {e}")
        return {"error": "Internal server error"}


@router.get("/health")
async def overall_health():
    """
    Overall system health check including cache status.
    """
    cache_status = await cache_health()

    return {
        "status": "healthy" if cache_status["overall_health"] else "degraded",
        "cache": cache_status,
        "message": "System operational" if cache_status["overall_health"] else "Running without cache (slower responses)"
    }
