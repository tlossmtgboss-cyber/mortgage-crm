# backend/utils/logger.py
"""
Structured logging for cache operations and performance tracking.
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

# Configure logger
logger = logging.getLogger("perennia.cache")


class CacheLogger:
    """Structured logging for cache operations"""

    def __init__(self, logger_name: str = "perennia.cache"):
        self.logger = logging.getLogger(logger_name)

    def _log(self, level: str, data: Dict[str, Any]):
        """Internal log method with JSON formatting"""
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(json.dumps(data))

    def log_hit(
        self,
        cache_type: str,
        query: str,
        ttl_remaining: Optional[int] = None,
        user_id: Optional[str] = None
    ):
        """Log cache hit event"""
        self._log("info", {
            "event": "cache_hit",
            "cache_type": cache_type,
            "query_preview": query[:50] + "..." if len(query) > 50 else query,
            "ttl_remaining": ttl_remaining,
            "user_id": user_id
        })

    def log_miss(
        self,
        cache_type: str,
        query: str,
        user_id: Optional[str] = None
    ):
        """Log cache miss event"""
        self._log("info", {
            "event": "cache_miss",
            "cache_type": cache_type,
            "query_preview": query[:50] + "..." if len(query) > 50 else query,
            "user_id": user_id
        })

    def log_set(
        self,
        cache_type: str,
        query: str,
        intent: str,
        ttl: int,
        user_id: Optional[str] = None
    ):
        """Log cache set event"""
        self._log("info", {
            "event": "cache_set",
            "cache_type": cache_type,
            "query_preview": query[:50] + "..." if len(query) > 50 else query,
            "intent": intent,
            "ttl": ttl,
            "user_id": user_id
        })

    def log_invalidation(
        self,
        cache_type: str,
        reason: str,
        count: int,
        pattern: Optional[str] = None
    ):
        """Log cache invalidation event"""
        self._log("info", {
            "event": "cache_invalidation",
            "cache_type": cache_type,
            "reason": reason,
            "keys_invalidated": count,
            "pattern": pattern
        })

    def log_error(
        self,
        cache_type: str,
        operation: str,
        error: str,
        query: Optional[str] = None
    ):
        """Log cache error event"""
        self._log("error", {
            "event": "cache_error",
            "cache_type": cache_type,
            "operation": operation,
            "error": error,
            "query_preview": (query[:50] + "..." if query and len(query) > 50 else query)
        })

    def log_connection(
        self,
        cache_type: str,
        status: str,
        redis_url: Optional[str] = None
    ):
        """Log cache connection event"""
        # Sanitize URL to remove credentials
        safe_url = None
        if redis_url:
            safe_url = redis_url.split("@")[-1] if "@" in redis_url else redis_url

        self._log("info", {
            "event": "cache_connection",
            "cache_type": cache_type,
            "status": status,
            "redis_host": safe_url
        })

    def log_performance(
        self,
        cache_type: str,
        operation: str,
        duration_ms: float,
        success: bool = True
    ):
        """Log cache operation performance"""
        self._log("debug", {
            "event": "cache_performance",
            "cache_type": cache_type,
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success
        })


# Global cache logger instance
cache_logger = CacheLogger()


# Convenience functions for direct logging
def log_cache_hit(query: str, cache_type: str = "response", **kwargs):
    cache_logger.log_hit(cache_type, query, **kwargs)


def log_cache_miss(query: str, cache_type: str = "response", **kwargs):
    cache_logger.log_miss(cache_type, query, **kwargs)


def log_cache_set(query: str, intent: str, ttl: int, cache_type: str = "response", **kwargs):
    cache_logger.log_set(cache_type, query, intent, ttl, **kwargs)


def log_cache_invalidation(reason: str, count: int, cache_type: str = "response", **kwargs):
    cache_logger.log_invalidation(cache_type, reason, count, **kwargs)
