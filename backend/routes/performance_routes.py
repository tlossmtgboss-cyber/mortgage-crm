"""
Performance Monitoring API Routes
=================================
Endpoints for monitoring application performance:
- Slow query analysis
- Endpoint performance stats
- Database pool status
- Database scaling for 1000+ users
- Overall performance summary
"""

import json
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db, get_pool_status
from monitoring.performance_service import performance_service
from monitoring.alerts_config import get_monitors_summary, export_monitors_json
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    """Require valid authentication for performance monitoring endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(
        token=credentials.credentials, request=None, db=db
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


router = APIRouter(
    prefix="/api/v1/performance",
    tags=["Performance Monitoring"],
    dependencies=[Depends(_require_auth)],
)

# Initialize scaling service on first request
_scaling_initialized = False

async def _ensure_scaling_service():
    """Initialize database scaling service."""
    global _scaling_initialized
    if not _scaling_initialized:
        try:
            from services.database_scaling_service import db_scaling
            await db_scaling.initialize()
            _scaling_initialized = True
        except Exception as e:
            logger.warning(f"Could not initialize scaling service: {e}")


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
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

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
            "error": "Internal server error",
            "pool": get_pool_status()
        }


# ============================================================================
# ENHANCED DATABASE MONITORING DASHBOARD
# ============================================================================

@router.get("/database/dashboard")
async def get_database_dashboard(db: Session = Depends(get_db)):
    """
    Comprehensive database monitoring dashboard.

    Returns:
    - Connection pool status
    - Active query count
    - Database statistics
    - Background job status
    - Recommendations for issues
    """
    import time
    from sqlalchemy import text
    from datetime import datetime

    dashboard = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pool": get_pool_status(),
        "connectivity": {},
        "statistics": {},
        "active_queries": {},
        "background_jobs": {},
        "recommendations": []
    }

    # Test connectivity
    start = time.time()
    try:
        db.execute(text("SELECT 1")).fetchone()
        dashboard["connectivity"] = {
            "status": "connected",
            "latency_ms": round((time.time() - start) * 1000, 2)
        }
    except Exception as e:
        dashboard["connectivity"] = {
            "status": "error",
            "error": "Internal server error"
        }
        dashboard["recommendations"].append("DATABASE UNREACHABLE - Check connection settings")
        return dashboard

    # Get database statistics (PostgreSQL specific)
    try:
        stats = db.execute(text("""
            SELECT
                numbackends as active_connections,
                xact_commit as transactions_committed,
                xact_rollback as transactions_rolled_back,
                blks_read as disk_blocks_read,
                blks_hit as cache_hits,
                tup_returned as rows_returned,
                tup_fetched as rows_fetched,
                tup_inserted as rows_inserted,
                tup_updated as rows_updated,
                tup_deleted as rows_deleted,
                deadlocks
            FROM pg_stat_database
            WHERE datname = current_database()
        """)).fetchone()

        if stats:
            total_blocks = (stats.disk_blocks_read or 0) + (stats.cache_hits or 0)
            cache_hit_ratio = round((stats.cache_hits or 0) / total_blocks * 100, 2) if total_blocks > 0 else 0

            dashboard["statistics"] = {
                "active_connections": stats.active_connections,
                "transactions_committed": stats.transactions_committed,
                "transactions_rolled_back": stats.transactions_rolled_back,
                "cache_hit_ratio_percent": cache_hit_ratio,
                "rows_returned": stats.rows_returned,
                "deadlocks": stats.deadlocks
            }

            # Connection warnings
            if stats.active_connections > 80:
                dashboard["recommendations"].append(
                    f"HIGH CONNECTION COUNT: {stats.active_connections} active connections (>80 threshold)"
                )

            if cache_hit_ratio < 95:
                dashboard["recommendations"].append(
                    f"LOW CACHE HIT RATIO: {cache_hit_ratio}% (should be >95%)"
                )

            if stats.deadlocks > 0:
                dashboard["recommendations"].append(
                    f"DEADLOCKS DETECTED: {stats.deadlocks} deadlocks in database history"
                )

    except Exception as e:
        dashboard["statistics"] = {"error": "Internal server error"}

    # Get active/long-running queries
    try:
        active = db.execute(text("""
            SELECT
                pid,
                usename as username,
                application_name,
                client_addr,
                state,
                EXTRACT(EPOCH FROM (now() - query_start))::int as duration_seconds,
                LEFT(query, 200) as query_preview,
                wait_event_type,
                wait_event
            FROM pg_stat_activity
            WHERE state != 'idle'
                AND pid != pg_backend_pid()
                AND query NOT LIKE '%pg_stat_activity%'
            ORDER BY query_start ASC
            LIMIT 20
        """)).fetchall()

        long_running = [
            {
                "pid": q.pid,
                "username": q.username,
                "application": q.application_name,
                "state": q.state,
                "duration_seconds": q.duration_seconds,
                "query_preview": q.query_preview,
                "waiting_on": f"{q.wait_event_type}: {q.wait_event}" if q.wait_event_type else None
            }
            for q in active if q.duration_seconds and q.duration_seconds > 5
        ]

        dashboard["active_queries"] = {
            "total_active": len(active),
            "long_running_count": len(long_running),
            "long_running": long_running
        }

        if len(long_running) > 3:
            dashboard["recommendations"].append(
                f"LONG-RUNNING QUERIES: {len(long_running)} queries running >5 seconds"
            )

    except Exception as e:
        dashboard["active_queries"] = {"error": "Internal server error"}

    # Get background job status
    try:
        from services.scheduler_service import scheduler_service
        jobs = scheduler_service.get_job_status()
        dashboard["background_jobs"] = {
            "total_jobs": len(jobs),
            "jobs": jobs[:10]  # Limit to first 10
        }
    except Exception as e:
        dashboard["background_jobs"] = {"error": "Internal server error"}

    # Overall health status
    pool_status = dashboard["pool"].get("status", "unknown")
    conn_status = dashboard["connectivity"].get("status", "unknown")

    if pool_status == "healthy" and conn_status == "connected" and len(dashboard["recommendations"]) == 0:
        dashboard["overall_status"] = "healthy"
    elif len(dashboard["recommendations"]) > 2:
        dashboard["overall_status"] = "critical"
    else:
        dashboard["overall_status"] = "warning" if dashboard["recommendations"] else "healthy"

    return dashboard


@router.get("/database/connections")
async def get_connection_details(db: Session = Depends(get_db)):
    """
    Get detailed breakdown of all database connections.

    Shows:
    - Connections by state
    - Connections by application
    - Idle connection age
    """
    from sqlalchemy import text

    try:
        # Connections by state
        by_state = db.execute(text("""
            SELECT
                state,
                COUNT(*) as count
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state
            ORDER BY count DESC
        """)).fetchall()

        # Connections by application
        by_app = db.execute(text("""
            SELECT
                COALESCE(application_name, 'unknown') as application,
                COUNT(*) as count,
                COUNT(CASE WHEN state = 'idle' THEN 1 END) as idle_count,
                COUNT(CASE WHEN state = 'active' THEN 1 END) as active_count
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY application_name
            ORDER BY count DESC
            LIMIT 20
        """)).fetchall()

        # Oldest idle connections
        old_idle = db.execute(text("""
            SELECT
                pid,
                application_name,
                state,
                EXTRACT(EPOCH FROM (now() - state_change))::int as idle_seconds
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND state = 'idle'
                AND state_change < now() - interval '5 minutes'
            ORDER BY state_change ASC
            LIMIT 10
        """)).fetchall()

        return {
            "by_state": [{"state": r.state or "null", "count": r.count} for r in by_state],
            "by_application": [
                {
                    "application": r.application,
                    "total": r.count,
                    "idle": r.idle_count,
                    "active": r.active_count
                }
                for r in by_app
            ],
            "stale_idle_connections": [
                {
                    "pid": r.pid,
                    "application": r.application_name,
                    "idle_minutes": round(r.idle_seconds / 60, 1)
                }
                for r in old_idle
            ],
            "total_connections": sum(r.count for r in by_state)
        }

    except Exception as e:
        logger.error(f"Failed to get connection details: {e}")
        return {"error": "Internal server error"}


@router.post("/database/terminate-idle")
async def terminate_idle_connections(
    older_than_minutes: int = Query(30, ge=5, le=120, description="Terminate idle connections older than X minutes"),
    db: Session = Depends(get_db)
):
    """
    Terminate idle database connections older than specified time.

    Use with caution - this will forcibly close idle connections.
    """
    from sqlalchemy import text

    try:
        # Find and terminate old idle connections
        result = db.execute(text("""
            SELECT pg_terminate_backend(pid), pid, application_name
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND state = 'idle'
                AND state_change < now() - interval ':minutes minutes'
                AND pid != pg_backend_pid()
        """), {"minutes": older_than_minutes})

        terminated = result.fetchall()
        db.commit()

        return {
            "success": True,
            "terminated_count": len(terminated),
            "terminated_pids": [r.pid for r in terminated],
            "threshold_minutes": older_than_minutes
        }

    except Exception as e:
        logger.error(f"Failed to terminate idle connections: {e}")
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# DATABASE SCALING (1000+ USERS)
# ============================================================================

@router.get("/scaling/status")
async def get_scaling_status(db: Session = Depends(get_db)):
    """
    Get database scaling status for 1000+ user readiness.

    Returns:
    - Connection usage and capacity
    - Cache status
    - Scaling recommendations
    - Estimated user capacity
    """
    await _ensure_scaling_service()

    try:
        from services.database_scaling_service import db_scaling
        return await db_scaling.get_health_status(db)
    except Exception as e:
        logger.error(f"Scaling status check failed: {e}")
        return {"error": "Internal server error", "status": "unknown"}


@router.get("/scaling/report")
async def get_scaling_report(db: Session = Depends(get_db)):
    """
    Generate comprehensive scaling report for 1000+ users.

    Analyzes current infrastructure and identifies:
    - Gaps that need to be addressed
    - Action items with priorities
    - Readiness assessment
    """
    await _ensure_scaling_service()

    try:
        from services.database_scaling_service import db_scaling
        return await db_scaling.get_scaling_report(db)
    except Exception as e:
        logger.error(f"Scaling report generation failed: {e}")
        return {"error": "Internal server error"}


@router.get("/scaling/alerts")
async def get_scaling_alerts():
    """
    Get recent database scaling alerts.

    Returns alerts triggered when connection usage exceeds thresholds.
    """
    await _ensure_scaling_service()

    try:
        from services.database_scaling_service import db_scaling

        if not db_scaling._enabled:
            return {"alerts": [], "note": "Redis not connected, no alert history"}

        alerts_raw = await db_scaling.redis.lrange("db_scaling:alerts", 0, 49)
        alerts = []
        for alert_str in alerts_raw:
            try:
                alerts.append(json.loads(alert_str))
            except Exception as e:
                logger.error(f"Error parsing alert JSON: {e}")
                continue

        return {
            "alerts": alerts,
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Failed to get scaling alerts: {e}")
        return {"error": "Internal server error"}


@router.post("/scaling/cache/invalidate")
async def invalidate_scaling_cache(
    user_id: Optional[str] = Query(None, description="User ID to invalidate cache for"),
    query_type: Optional[str] = Query(None, description="Query type to invalidate")
):
    """
    Invalidate database scaling cache.

    Use when data has changed and cache needs refreshing.
    """
    await _ensure_scaling_service()

    try:
        from services.database_scaling_service import db_scaling

        if not db_scaling._enabled:
            return {"success": False, "reason": "Redis not connected"}

        if user_id:
            count = await db_scaling.invalidate_user_cache(user_id)
            return {"success": True, "invalidated": count, "scope": f"user:{user_id}"}
        elif query_type:
            await db_scaling.invalidate_cache(query_type)
            return {"success": True, "scope": f"query_type:{query_type}"}
        else:
            return {"success": False, "reason": "Specify user_id or query_type"}

    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        return {"success": False, "error": "Internal server error"}


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
            "error": "Internal server error"
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
