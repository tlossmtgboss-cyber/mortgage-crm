"""
Performance Monitoring API Routes
=================================
Endpoints for monitoring application performance:
- Slow query analysis
- Endpoint performance stats
- Database pool status
- Overall performance summary
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from database import get_db, get_pool_status
from monitoring.performance_service import performance_service
from monitoring.alerts_config import get_monitors_summary, export_monitors_json
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/performance", tags=["Performance Monitoring"])


# ============================================================================
# PERFORMANCE SUMMARY
# ============================================================================

@router.get("/summary")
async def get_performance_summary():
    """
    Get overall performance summary.

    Returns:
    - Uptime
    - Request totals and error rates
    - Slow query counts
    - Slowest endpoints
    """
    return performance_service.get_performance_summary()


@router.get("/health")
async def performance_health():
    """
    Quick health check with key performance metrics.

    Returns simple health status based on:
    - Error rate < 5%
    - Avg response time < 2000ms
    - Slow query count reasonable
    """
    summary = performance_service.get_performance_summary()

    # Health criteria
    error_rate_ok = summary["error_rate_percent"] < 5
    response_time_ok = summary["avg_response_time_ms"] < 2000
    slow_queries_ok = summary["slow_query_count"] < 100

    status = "healthy" if all([error_rate_ok, response_time_ok, slow_queries_ok]) else "degraded"

    return {
        "status": status,
        "checks": {
            "error_rate": {
                "ok": error_rate_ok,
                "value": summary["error_rate_percent"],
                "threshold": 5
            },
            "response_time": {
                "ok": response_time_ok,
                "value": summary["avg_response_time_ms"],
                "threshold": 2000
            },
            "slow_queries": {
                "ok": slow_queries_ok,
                "value": summary["slow_query_count"],
                "threshold": 100
            }
        },
        "uptime_seconds": summary["uptime_seconds"],
        "total_requests": summary["total_requests"]
    }


# ============================================================================
# SLOW QUERY ANALYSIS
# ============================================================================

@router.get("/slow-queries")
async def get_slow_queries(
    limit: int = Query(50, ge=1, le=200, description="Max queries to return"),
    min_duration_ms: Optional[float] = Query(None, description="Minimum duration filter"),
    hours: Optional[int] = Query(None, description="Only queries from last N hours")
):
    """
    Get list of recent slow database queries.

    Returns individual slow query records sorted by duration.
    """
    since = None
    if hours:
        since = datetime.utcnow() - timedelta(hours=hours)

    return {
        "queries": performance_service.get_slow_queries(
            limit=limit,
            min_duration_ms=min_duration_ms,
            since=since
        ),
        "threshold_ms": performance_service._slow_queries.maxlen and 500,
        "filters": {
            "limit": limit,
            "min_duration_ms": min_duration_ms,
            "hours": hours
        }
    }


@router.get("/slow-queries/report")
async def get_slow_query_report():
    """
    Get aggregated slow query report.

    Groups similar queries and shows:
    - Count of occurrences
    - Total time spent
    - Average duration
    - Worst offenders
    """
    return performance_service.get_slow_query_report()


# ============================================================================
# ENDPOINT PERFORMANCE
# ============================================================================

@router.get("/endpoints")
async def get_endpoint_stats(
    sort_by: str = Query(
        "avg_duration",
        enum=["avg_duration", "total_requests", "error_rate", "slow_count"],
        description="Sort field"
    ),
    limit: int = Query(50, ge=1, le=200, description="Max endpoints to return")
):
    """
    Get performance statistics for all endpoints.

    Stats include:
    - Request count
    - Average/min/max duration
    - Error rate
    - Slow request count
    """
    stats = performance_service.get_endpoint_stats(sort_by=sort_by)
    return {
        "endpoints": stats[:limit],
        "total_endpoints": len(stats),
        "sort_by": sort_by
    }


@router.get("/endpoints/slow")
async def get_slow_endpoints(
    limit: int = Query(50, ge=1, le=200, description="Max records to return")
):
    """
    Get list of slow endpoint requests.

    Returns individual slow request records.
    """
    return {
        "endpoints": performance_service.get_slow_endpoints(limit=limit),
        "threshold_ms": 2000  # SLOW_ENDPOINT_THRESHOLD_MS
    }


# ============================================================================
# DATABASE MONITORING
# ============================================================================

@router.get("/database/pool")
async def get_database_pool_status():
    """
    Get database connection pool status.

    Returns:
    - Pool size and configuration
    - Checked in/out connections
    - Overflow count
    - Health status
    """
    return get_pool_status()


@router.get("/database/health")
async def check_database_health(db: Session = Depends(get_db)):
    """
    Check database connectivity and basic health.

    Performs a simple query to verify database is responsive.
    """
    import time
    from sqlalchemy import text

    start = time.time()
    try:
        result = db.execute(text("SELECT 1")).fetchone()
        duration_ms = (time.time() - start) * 1000

        pool_status = get_pool_status()

        return {
            "status": "healthy",
            "query_response_ms": round(duration_ms, 2),
            "pool": pool_status
        }

    except SQLAlchemyError as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "pool": get_pool_status()
        }


# ============================================================================
# ALERTS CONFIGURATION
# ============================================================================

@router.get("/alerts/summary")
async def get_alerts_summary():
    """
    Get summary of configured DataDog alerts.

    Returns:
    - Total monitors configured
    - Monitors by category
    - Monitors by priority
    """
    return get_monitors_summary()


@router.post("/alerts/export")
async def export_alerts_config(filename: str = Query("datadog_monitors.json")):
    """
    Export DataDog monitor configurations to JSON file.

    The exported file can be used with:
    - DataDog Terraform provider
    - DataDog API manual import
    """
    try:
        filepath = export_monitors_json(filename)
        return {
            "success": True,
            "file": filepath,
            "monitors_exported": len(get_monitors_summary()["monitors"])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# ADMIN OPERATIONS
# ============================================================================

@router.post("/clear-stats")
async def clear_performance_stats():
    """
    Clear all collected performance statistics.

    Warning: This will reset all counters and collected data.
    Use for testing or after deployments.
    """
    performance_service.clear_stats()
    return {
        "success": True,
        "message": "Performance statistics cleared"
    }
