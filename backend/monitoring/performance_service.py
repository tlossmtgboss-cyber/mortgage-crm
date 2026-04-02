"""
Performance Monitoring Service
==============================
Centralized performance monitoring with:
- Slow query tracking and persistence
- Endpoint performance aggregation
- Database pool monitoring
- Performance threshold alerts
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass, field, asdict
from threading import Lock

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

SLOW_QUERY_THRESHOLD_MS = float(os.getenv("SLOW_QUERY_THRESHOLD_MS", "500"))
SLOW_ENDPOINT_THRESHOLD_MS = float(os.getenv("SLOW_ENDPOINT_THRESHOLD_MS", "2000"))
MAX_SLOW_QUERIES_STORED = int(os.getenv("MAX_SLOW_QUERIES_STORED", "1000"))
MAX_SLOW_ENDPOINTS_STORED = int(os.getenv("MAX_SLOW_ENDPOINTS_STORED", "500"))


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class SlowQuery:
    """Record of a slow database query."""
    query: str
    duration_ms: float
    timestamp: datetime
    params_hash: str = ""

    def to_dict(self) -> Dict:
        return {
            "query": self.query[:500] + "..." if len(self.query) > 500 else self.query,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "params_hash": self.params_hash
        }


@dataclass
class SlowEndpoint:
    """Record of a slow API endpoint."""
    path: str
    method: str
    duration_ms: float
    status_code: int
    timestamp: datetime
    user_id: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "method": self.method,
            "duration_ms": round(self.duration_ms, 2),
            "status_code": self.status_code,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id
        }


@dataclass
class EndpointStats:
    """Aggregated stats for an endpoint."""
    path: str
    method: str
    total_requests: int = 0
    total_duration_ms: float = 0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0
    error_count: int = 0
    slow_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update(self, duration_ms: float, status_code: int):
        self.total_requests += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        if status_code >= 500:
            self.error_count += 1
        if duration_ms > SLOW_ENDPOINT_THRESHOLD_MS:
            self.slow_count += 1
        self.last_updated = datetime.now(timezone.utc)

    @property
    def avg_duration_ms(self) -> float:
        if self.total_requests == 0:
            return 0
        return self.total_duration_ms / self.total_requests

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0
        return (self.error_count / self.total_requests) * 100

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "method": self.method,
            "total_requests": self.total_requests,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float('inf') else 0,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "error_count": self.error_count,
            "error_rate_percent": round(self.error_rate, 2),
            "slow_count": self.slow_count,
            "last_updated": self.last_updated.isoformat()
        }


# ============================================================================
# PERFORMANCE SERVICE
# ============================================================================

class PerformanceService:
    """
    Centralized service for tracking application performance.

    Usage:
        performance = PerformanceService()
        performance.record_slow_query(query, duration_ms)
        performance.record_endpoint(path, method, duration_ms, status_code)

        # Get reports
        performance.get_slow_query_report()
        performance.get_endpoint_stats()
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._slow_queries: deque = deque(maxlen=MAX_SLOW_QUERIES_STORED)
        self._slow_endpoints: deque = deque(maxlen=MAX_SLOW_ENDPOINTS_STORED)
        self._endpoint_stats: Dict[str, EndpointStats] = {}
        self._stats_lock = Lock()
        self._queries_lock = Lock()
        self._started_at = datetime.now(timezone.utc)

        self._initialized = True
        logger.info("Performance monitoring service initialized")

    # ========================================================================
    # SLOW QUERY TRACKING
    # ========================================================================

    def record_slow_query(self, query: str, duration_ms: float, params_hash: str = ""):
        """Record a slow database query."""
        if duration_ms < SLOW_QUERY_THRESHOLD_MS:
            return

        record = SlowQuery(
            query=query,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc),
            params_hash=params_hash
        )

        with self._queries_lock:
            self._slow_queries.append(record)

        logger.warning(
            f"Slow query recorded ({duration_ms:.1f}ms): "
            f"{query[:100]}..."
        )

    def get_slow_queries(
        self,
        limit: int = 50,
        min_duration_ms: float = None,
        since: datetime = None
    ) -> List[Dict]:
        """Get recent slow queries."""
        with self._queries_lock:
            queries = list(self._slow_queries)

        # Apply filters
        if min_duration_ms:
            queries = [q for q in queries if q.duration_ms >= min_duration_ms]
        if since:
            queries = [q for q in queries if q.timestamp >= since]

        # Sort by duration (slowest first)
        queries.sort(key=lambda x: x.duration_ms, reverse=True)

        return [q.to_dict() for q in queries[:limit]]

    def get_slow_query_report(self) -> Dict:
        """Get aggregated slow query report."""
        with self._queries_lock:
            queries = list(self._slow_queries)

        if not queries:
            return {
                "total_slow_queries": 0,
                "threshold_ms": SLOW_QUERY_THRESHOLD_MS,
                "message": "No slow queries recorded"
            }

        # Aggregate by query pattern
        patterns: Dict[str, Dict] = {}
        for q in queries:
            # Normalize query for grouping
            normalized = self._normalize_query(q.query)

            if normalized not in patterns:
                patterns[normalized] = {
                    "count": 0,
                    "total_ms": 0,
                    "max_ms": 0,
                    "example": q.query[:200]
                }

            patterns[normalized]["count"] += 1
            patterns[normalized]["total_ms"] += q.duration_ms
            patterns[normalized]["max_ms"] = max(patterns[normalized]["max_ms"], q.duration_ms)

        # Sort by total time
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: x[1]["total_ms"],
            reverse=True
        )

        return {
            "total_slow_queries": len(queries),
            "threshold_ms": SLOW_QUERY_THRESHOLD_MS,
            "unique_patterns": len(patterns),
            "worst_offenders": [
                {
                    "pattern": pattern[:100],
                    "count": data["count"],
                    "total_ms": round(data["total_ms"], 2),
                    "avg_ms": round(data["total_ms"] / data["count"], 2),
                    "max_ms": round(data["max_ms"], 2),
                    "example": data["example"]
                }
                for pattern, data in sorted_patterns[:10]
            ]
        }

    def _normalize_query(self, query: str) -> str:
        """Normalize query for grouping similar queries."""
        import re
        # Replace literal values with placeholders
        normalized = re.sub(r"'[^']*'", "'?'", query)
        normalized = re.sub(r"\b\d+\b", "?", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized[:200]

    # ========================================================================
    # ENDPOINT TRACKING
    # ========================================================================

    def record_endpoint(
        self,
        path: str,
        method: str,
        duration_ms: float,
        status_code: int,
        user_id: int = None
    ):
        """Record an endpoint request."""
        # Normalize path
        import re
        normalized_path = re.sub(r'/\d+', '/{id}', path)
        normalized_path = re.sub(r'/[a-f0-9-]{36}', '/{uuid}', normalized_path)

        key = f"{method}:{normalized_path}"

        with self._stats_lock:
            if key not in self._endpoint_stats:
                self._endpoint_stats[key] = EndpointStats(
                    path=normalized_path,
                    method=method
                )
            self._endpoint_stats[key].update(duration_ms, status_code)

        # Record slow endpoint
        if duration_ms > SLOW_ENDPOINT_THRESHOLD_MS:
            record = SlowEndpoint(
                path=path,
                method=method,
                duration_ms=duration_ms,
                status_code=status_code,
                timestamp=datetime.now(timezone.utc),
                user_id=user_id
            )
            self._slow_endpoints.append(record)

            logger.warning(
                f"Slow endpoint: {method} {path} ({duration_ms:.1f}ms)"
            )

    def get_endpoint_stats(self, sort_by: str = "avg_duration") -> List[Dict]:
        """Get endpoint performance statistics."""
        with self._stats_lock:
            stats = list(self._endpoint_stats.values())

        # Sort options
        if sort_by == "avg_duration":
            stats.sort(key=lambda x: x.avg_duration_ms, reverse=True)
        elif sort_by == "total_requests":
            stats.sort(key=lambda x: x.total_requests, reverse=True)
        elif sort_by == "error_rate":
            stats.sort(key=lambda x: x.error_rate, reverse=True)
        elif sort_by == "slow_count":
            stats.sort(key=lambda x: x.slow_count, reverse=True)

        return [s.to_dict() for s in stats]

    def get_slow_endpoints(self, limit: int = 50) -> List[Dict]:
        """Get recent slow endpoint requests."""
        endpoints = list(self._slow_endpoints)
        endpoints.sort(key=lambda x: x.duration_ms, reverse=True)
        return [e.to_dict() for e in endpoints[:limit]]

    # ========================================================================
    # OVERALL METRICS
    # ========================================================================

    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        with self._stats_lock:
            stats = list(self._endpoint_stats.values())

        total_requests = sum(s.total_requests for s in stats)
        total_errors = sum(s.error_count for s in stats)
        total_slow = sum(s.slow_count for s in stats)

        # Calculate weighted average response time
        if total_requests > 0:
            weighted_avg = sum(s.total_duration_ms for s in stats) / total_requests
        else:
            weighted_avg = 0

        # Get slowest endpoints
        stats.sort(key=lambda x: x.avg_duration_ms, reverse=True)
        slowest = stats[:5]

        # Get most erroring endpoints
        stats.sort(key=lambda x: x.error_rate, reverse=True)
        most_errors = [s for s in stats[:5] if s.error_count > 0]

        return {
            "uptime_seconds": (datetime.now(timezone.utc) - self._started_at).total_seconds(),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate_percent": round((total_errors / total_requests) * 100, 2) if total_requests > 0 else 0,
            "total_slow_requests": total_slow,
            "avg_response_time_ms": round(weighted_avg, 2),
            "slow_query_count": len(self._slow_queries),
            "thresholds": {
                "slow_query_ms": SLOW_QUERY_THRESHOLD_MS,
                "slow_endpoint_ms": SLOW_ENDPOINT_THRESHOLD_MS
            },
            "slowest_endpoints": [s.to_dict() for s in slowest],
            "highest_error_endpoints": [s.to_dict() for s in most_errors]
        }

    def clear_stats(self):
        """Clear all collected statistics (for testing)."""
        with self._stats_lock:
            self._endpoint_stats.clear()
        with self._queries_lock:
            self._slow_queries.clear()
        self._slow_endpoints.clear()
        self._started_at = datetime.now(timezone.utc)
        logger.info("Performance statistics cleared")


# Global instance
performance_service = PerformanceService()


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

class PerformanceMiddleware:
    """
    FastAPI middleware for automatic endpoint performance tracking.

    Usage:
        from monitoring.performance_service import PerformanceMiddleware
        app.add_middleware(PerformanceMiddleware)
    """

    def __init__(self, app, exclude_paths: List[str] = None):
        self.app = app
        self.exclude_paths = exclude_paths or [
            "/health", "/metrics", "/docs", "/redoc", "/openapi.json",
            "/monitoring/", "/favicon.ico"
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start_time = time.time()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.time() - start_time) * 1000

            # Extract user_id from scope if available
            user_id = None
            if "state" in scope and hasattr(scope["state"], "user_id"):
                user_id = scope["state"].user_id

            performance_service.record_endpoint(
                path=path,
                method=method,
                duration_ms=duration_ms,
                status_code=status_code,
                user_id=user_id
            )
