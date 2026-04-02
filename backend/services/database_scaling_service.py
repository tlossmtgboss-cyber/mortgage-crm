"""
Database Scaling Service for 1000+ Users
========================================

Provides:
1. Connection monitoring with alerts
2. Query result caching for high-frequency endpoints
3. Connection pool health checks
4. Scaling recommendations

Usage:
    from services.database_scaling_service import db_scaling

    # Check if we're approaching connection limits
    health = await db_scaling.get_health_status(db)

    # Cache expensive query results
    result = await db_scaling.cached_query(
        db, "pipeline_summary", user_id,
        lambda: expensive_query(db, user_id)
    )
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, TypeVar
from functools import wraps

import redis.asyncio as redis
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DatabaseScalingService:
    """
    Service to ensure database can scale to 1000+ users.

    Key strategies:
    1. Aggressive Redis caching for repeated queries
    2. Connection monitoring and alerts
    3. Query deduplication during high load
    4. Automatic scaling recommendations
    """

    # Connection thresholds for Railway Pro (~100 connection limit)
    CONNECTION_WARNING_THRESHOLD = 70  # 70% of limit
    CONNECTION_CRITICAL_THRESHOLD = 85  # 85% of limit
    CONNECTION_LIMIT = 100  # Railway Pro typical limit

    # Cache TTLs for different query types (seconds)
    CACHE_TTL = {
        "user_session": 300,        # 5 min - user authentication data
        "pipeline_summary": 60,     # 1 min - changes frequently
        "pipeline_detail": 120,     # 2 min - loan/lead details
        "team_members": 600,        # 10 min - rarely changes
        "permissions": 300,         # 5 min - permission checks
        "settings": 900,            # 15 min - user/company settings
        "metrics": 180,             # 3 min - performance metrics
        "notifications": 60,        # 1 min - active notifications
        "default": 300,             # 5 min default
    }

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis: Optional[redis.Redis] = None
        self._enabled = False
        self._connection_lock = asyncio.Lock()
        self._alert_cooldown: Dict[str, datetime] = {}

    async def initialize(self):
        """Initialize Redis connection for scaling features."""
        async with self._connection_lock:
            if self._enabled:
                return True

            try:
                self.redis = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                    max_connections=20,
                    retry_on_timeout=True
                )
                await self.redis.ping()
                self._enabled = True
                logger.info("[DB_SCALING] Redis connected for database scaling")
                return True
            except Exception as e:
                logger.warning(f"[DB_SCALING] Redis unavailable: {e}")
                self._enabled = False
                return False

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            try:
                await self.redis.aclose()
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            self.redis = None
            self._enabled = False

    # =========================================================================
    # CONNECTION MONITORING
    # =========================================================================

    async def get_connection_status(self, db: Session) -> Dict[str, Any]:
        """
        Get current database connection status with alerts.

        Returns connection count, usage percentage, and any alerts.
        """
        try:
            result = db.execute(text("""
                SELECT
                    numbackends as active_connections,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
                FROM pg_stat_database
                WHERE datname = current_database()
            """)).fetchone()

            if not result:
                return {"error": "Could not fetch connection stats"}

            active = result.active_connections or 0
            max_conn = result.max_connections or self.CONNECTION_LIMIT
            usage_pct = round((active / max_conn) * 100, 1)

            status = {
                "active_connections": active,
                "max_connections": max_conn,
                "usage_percent": usage_pct,
                "status": "healthy",
                "alerts": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Check thresholds
            if usage_pct >= self.CONNECTION_CRITICAL_THRESHOLD:
                status["status"] = "critical"
                status["alerts"].append({
                    "level": "critical",
                    "message": f"Connection usage at {usage_pct}% - immediate action required",
                    "recommendation": "Scale database or reduce connection usage"
                })
                await self._send_alert("connection_critical", f"DB connections at {usage_pct}%")

            elif usage_pct >= self.CONNECTION_WARNING_THRESHOLD:
                status["status"] = "warning"
                status["alerts"].append({
                    "level": "warning",
                    "message": f"Connection usage at {usage_pct}% - approaching limit",
                    "recommendation": "Monitor closely, consider scaling"
                })
                await self._send_alert("connection_warning", f"DB connections at {usage_pct}%")

            return status

        except Exception as e:
            logger.error(f"[DB_SCALING] Connection status check failed: {e}")
            return {"error": "Internal server error", "status": "unknown"}

    async def _send_alert(self, alert_type: str, message: str):
        """Send alert with cooldown to prevent spam."""
        cooldown_key = f"alert_{alert_type}"
        now = datetime.now(timezone.utc)

        # Check cooldown (5 minutes between same alerts)
        if cooldown_key in self._alert_cooldown:
            if now - self._alert_cooldown[cooldown_key] < timedelta(minutes=5):
                return  # Still in cooldown

        self._alert_cooldown[cooldown_key] = now
        logger.warning(f"[DB_SCALING ALERT] {alert_type}: {message}")

        # Store alert in Redis for dashboard
        if self._enabled:
            try:
                alert_data = {
                    "type": alert_type,
                    "message": message,
                    "timestamp": now.isoformat()
                }
                await self.redis.lpush("db_scaling:alerts", json.dumps(alert_data))
                await self.redis.ltrim("db_scaling:alerts", 0, 99)  # Keep last 100
            except Exception as e:
                logger.error(f"Error storing alert in Redis: {e}")

    # =========================================================================
    # QUERY CACHING
    # =========================================================================

    def _cache_key(self, query_type: str, user_id: Optional[str] = None, **kwargs) -> str:
        """Generate cache key for a query."""
        key_parts = ["dbscale", query_type]
        if user_id:
            key_parts.append(f"user:{user_id}")
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return ":".join(key_parts)

    async def cached_query(
        self,
        query_type: str,
        query_fn: Callable[[], T],
        user_id: Optional[str] = None,
        ttl: Optional[int] = None,
        **cache_params
    ) -> T:
        """
        Execute a query with caching.

        Args:
            query_type: Type of query (for TTL selection)
            query_fn: Function that executes the query
            user_id: Optional user ID for cache isolation
            ttl: Override TTL (seconds)
            **cache_params: Additional params for cache key

        Returns:
            Query result (from cache or fresh)
        """
        # If Redis not available, just execute query
        if not self._enabled:
            return query_fn()

        cache_key = self._cache_key(query_type, user_id, **cache_params)

        try:
            # Check cache
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"[DB_SCALING] Cache HIT: {query_type}")
                return json.loads(cached)

            # Execute query
            result = query_fn()

            # Cache result
            cache_ttl = ttl or self.CACHE_TTL.get(query_type, self.CACHE_TTL["default"])
            await self.redis.setex(
                cache_key,
                cache_ttl,
                json.dumps(result, default=str)
            )
            logger.debug(f"[DB_SCALING] Cache SET: {query_type} (TTL: {cache_ttl}s)")

            return result

        except json.JSONDecodeError:
            # Corrupted cache, delete and re-execute
            await self.redis.delete(cache_key)
            return query_fn()
        except Exception as e:
            logger.warning(f"[DB_SCALING] Cache error, falling back to DB: {e}")
            return query_fn()

    async def invalidate_cache(self, query_type: str, user_id: Optional[str] = None, **cache_params):
        """Invalidate a specific cached query."""
        if not self._enabled:
            return

        cache_key = self._cache_key(query_type, user_id, **cache_params)
        try:
            await self.redis.delete(cache_key)
            logger.debug(f"[DB_SCALING] Cache invalidated: {query_type}")
        except Exception as e:
            logger.warning(f"[DB_SCALING] Cache invalidation failed: {e}")

    async def invalidate_user_cache(self, user_id: str):
        """Invalidate all cached data for a user."""
        if not self._enabled:
            return 0

        try:
            pattern = f"dbscale:*:user:{user_id}*"
            deleted = 0
            cursor = 0

            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += await self.redis.delete(*keys)
                if cursor == 0:
                    break

            logger.info(f"[DB_SCALING] Invalidated {deleted} cache entries for user {user_id}")
            return deleted
        except Exception as e:
            logger.warning(f"[DB_SCALING] User cache invalidation failed: {e}")
            return 0

    # =========================================================================
    # HEALTH & RECOMMENDATIONS
    # =========================================================================

    async def get_health_status(self, db: Session) -> Dict[str, Any]:
        """
        Get comprehensive health status with scaling recommendations.

        Call this from health check endpoints to monitor scaling status.
        """
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "healthy",
            "components": {},
            "recommendations": [],
            "capacity_estimate": {}
        }

        # Connection status
        conn_status = await self.get_connection_status(db)
        status["components"]["connections"] = conn_status

        if conn_status.get("status") == "critical":
            status["overall_status"] = "critical"
        elif conn_status.get("status") == "warning":
            status["overall_status"] = "warning"

        # Cache status
        cache_status = await self._get_cache_status()
        status["components"]["cache"] = cache_status

        if not cache_status.get("enabled"):
            status["recommendations"].append({
                "priority": "high",
                "issue": "Redis cache not connected",
                "action": "Enable Redis for query caching to reduce database load"
            })

        # Capacity estimate
        active_conn = conn_status.get("active_connections", 0)
        max_conn = conn_status.get("max_connections", 100)

        # Rough estimate: each concurrent user needs ~0.2 connections on average
        # (due to connection pooling and request patterns)
        estimated_capacity = int((max_conn - 10) / 0.2)  # Reserve 10 for system
        current_load_pct = conn_status.get("usage_percent", 0)

        status["capacity_estimate"] = {
            "current_connections": active_conn,
            "max_connections": max_conn,
            "estimated_concurrent_users": estimated_capacity,
            "current_load_percent": current_load_pct,
            "headroom_users": int(estimated_capacity * (100 - current_load_pct) / 100)
        }

        # Scaling recommendations based on current load
        if current_load_pct > 60:
            status["recommendations"].append({
                "priority": "medium",
                "issue": f"Connection usage at {current_load_pct}%",
                "action": "Consider upgrading to Railway Team plan for more connections"
            })

        if not cache_status.get("enabled") and current_load_pct > 40:
            status["recommendations"].append({
                "priority": "high",
                "issue": "High DB load without caching",
                "action": "Enable Redis caching immediately to reduce database pressure"
            })

        # Check for stale connections
        try:
            stale = db.execute(text("""
                SELECT COUNT(*) as count
                FROM pg_stat_activity
                WHERE datname = current_database()
                    AND state = 'idle'
                    AND state_change < now() - interval '10 minutes'
            """)).scalar()

            if stale and stale > 5:
                status["recommendations"].append({
                    "priority": "low",
                    "issue": f"{stale} stale idle connections",
                    "action": "Consider running /api/v1/performance/database/terminate-idle"
                })
        except Exception as e:
            logger.error(f"Error checking stale idle connections: {e}")

        return status

    async def _get_cache_status(self) -> Dict[str, Any]:
        """Get Redis cache status."""
        if not self._enabled:
            return {"enabled": False, "reason": "Redis not connected"}

        try:
            info = await self.redis.info("stats")

            # Count scaling-related keys
            cursor = 0
            total_keys = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match="dbscale:*", count=100)
                total_keys += len(keys)
                if cursor == 0:
                    break

            total_ops = info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)
            hit_rate = round((info.get("keyspace_hits", 0) / total_ops * 100), 2) if total_ops > 0 else 0

            return {
                "enabled": True,
                "cached_queries": total_keys,
                "hit_rate_percent": hit_rate,
                "memory_used": info.get("used_memory_human", "unknown")
            }
        except Exception as e:
            return {"enabled": True, "error": "Internal server error"}

    async def get_scaling_report(self, db: Session) -> Dict[str, Any]:
        """
        Generate a comprehensive scaling report for 1000+ users.

        Use this to assess readiness for scale.
        """
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_users": 1000,
            "current_status": {},
            "requirements": {},
            "gaps": [],
            "action_items": []
        }

        # Current status
        health = await self.get_health_status(db)
        report["current_status"] = {
            "connections": health["components"].get("connections", {}),
            "cache": health["components"].get("cache", {}),
            "capacity": health.get("capacity_estimate", {})
        }

        # Requirements for 1000 users
        # Assume 20% concurrent = 200 users at once
        # Each concurrent user needs ~0.5 connections peak
        required_connections = 200 * 0.5 + 20  # 120 connections needed
        current_max = report["current_status"]["connections"].get("max_connections", 100)

        report["requirements"] = {
            "target_concurrent_users": 200,
            "required_connections": int(required_connections),
            "required_cache": True,
            "recommended_plan": "Railway Team" if required_connections > 100 else "Railway Pro"
        }

        # Identify gaps
        if current_max < required_connections:
            report["gaps"].append({
                "component": "connections",
                "current": current_max,
                "required": int(required_connections),
                "severity": "high"
            })
            report["action_items"].append({
                "priority": 1,
                "action": f"Upgrade database to support {int(required_connections)}+ connections",
                "options": [
                    "Upgrade to Railway Team plan",
                    "Use external PostgreSQL (AWS RDS, Supabase Pro)",
                    "Add read replicas for query distribution"
                ]
            })

        if not report["current_status"]["cache"].get("enabled"):
            report["gaps"].append({
                "component": "cache",
                "current": "disabled",
                "required": "enabled",
                "severity": "high"
            })
            report["action_items"].append({
                "priority": 2,
                "action": "Enable Redis caching",
                "expected_impact": "50-70% reduction in database queries"
            })

        # Ready assessment
        if not report["gaps"]:
            report["ready_for_scale"] = True
            report["summary"] = "System is ready for 1000+ users"
        elif len([g for g in report["gaps"] if g["severity"] == "high"]) > 0:
            report["ready_for_scale"] = False
            report["summary"] = "Critical gaps must be addressed before scaling"
        else:
            report["ready_for_scale"] = "partial"
            report["summary"] = "Minor improvements recommended before scaling"

        return report


# Global instance
db_scaling = DatabaseScalingService()


# Convenience decorator for cached queries
def cached(query_type: str, ttl: Optional[int] = None):
    """
    Decorator to cache function results.

    Usage:
        @cached("pipeline_summary")
        async def get_pipeline(db, user_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user_id from kwargs or args
            user_id = kwargs.get("user_id") or (args[1] if len(args) > 1 else None)

            return await db_scaling.cached_query(
                query_type=query_type,
                query_fn=lambda: func(*args, **kwargs),
                user_id=str(user_id) if user_id else None,
                ttl=ttl
            )
        return wrapper
    return decorator
