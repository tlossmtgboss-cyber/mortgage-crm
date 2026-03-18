"""
Database Connection Pool Monitor

Provides real-time monitoring of SQLAlchemy's connection pool for the
Perennia AI backend running on Railway (~20 connection limit).

Features:
- get_pool_stats(): Detailed pool metrics (size, checked_out, overflow, etc.)
- check_pool_health(): Health status with "healthy", "warning", "critical" levels
- Background task that logs pool stats every 60 seconds
- Warning log at >70% pool utilization
- Critical log at >90% pool utilization

Usage:
    from services.db_monitor import start_pool_monitor, get_pool_stats, check_pool_health

    # In startup event:
    start_pool_monitor()

    # In endpoints:
    stats = get_pool_stats()
    health = check_pool_health()
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Thresholds for pool utilization alerts
POOL_WARNING_THRESHOLD = 0.70   # 70% — emit warning log
POOL_CRITICAL_THRESHOLD = 0.90  # 90% — emit critical log

# Background monitor interval in seconds
MONITOR_INTERVAL_SECONDS = 60

# Module-level state
_monitor_thread: Optional[threading.Thread] = None
_monitor_running = False


def _get_engine():
    """Lazy import of the engine to avoid circular imports at module load."""
    from db import engine
    return engine


def get_pool_stats() -> Dict[str, Any]:
    """
    Get current connection pool statistics.

    Returns a dict with:
        - pool_type: "QueuePool" or "NullPool (PgBouncer)"
        - pool_size: Configured base pool size
        - checked_out: Connections currently in use
        - checked_in: Connections idle in pool
        - overflow: Current overflow connections beyond pool_size
        - max_overflow: Maximum allowed overflow
        - max_connections: Total maximum connections (pool_size + max_overflow)
        - total_connections: Current total connections (checked_out + checked_in)
        - utilization_pct: Percentage of max_connections currently checked out
        - pool_status_text: Raw status string from SQLAlchemy pool
        - timestamp: ISO timestamp of when stats were collected

    For NullPool (PgBouncer mode), returns limited info since SQLAlchemy
    doesn't manage the pool.
    """
    try:
        engine = _get_engine()
        pool = engine.pool

        now = datetime.now(timezone.utc).isoformat()

        # NullPool (PgBouncer mode) doesn't track connections
        if isinstance(pool, NullPool):
            return {
                "pool_type": "NullPool (PgBouncer)",
                "pool_size": 0,
                "checked_out": 0,
                "checked_in": 0,
                "overflow": 0,
                "max_overflow": 0,
                "max_connections": 0,
                "total_connections": 0,
                "utilization_pct": 0.0,
                "pool_status_text": "PgBouncer handles pooling externally",
                "timestamp": now,
                "note": "Connection pooling handled by PgBouncer — SQLAlchemy pool stats not applicable",
            }

        pool_size = pool.size()
        checked_out = pool.checkedout()
        checked_in = pool.checkedin()
        overflow = pool.overflow()
        max_overflow = pool._max_overflow
        max_connections = pool_size + max_overflow
        total_connections = checked_out + checked_in

        # Utilization is checked_out / max_connections
        utilization_pct = (checked_out / max_connections * 100) if max_connections > 0 else 0.0

        # Get raw status string
        try:
            pool_status_text = pool.status()
        except Exception:
            pool_status_text = "unavailable"

        return {
            "pool_type": "QueuePool",
            "pool_size": pool_size,
            "checked_out": checked_out,
            "checked_in": checked_in,
            "overflow": overflow,
            "max_overflow": max_overflow,
            "max_connections": max_connections,
            "total_connections": total_connections,
            "utilization_pct": round(utilization_pct, 1),
            "pool_status_text": pool_status_text,
            "timestamp": now,
        }

    except Exception as e:
        logger.exception(f"Failed to collect pool stats: {e}")
        return {
            "pool_type": "unknown",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def check_pool_health() -> Dict[str, Any]:
    """
    Assess connection pool health based on current utilization.

    Returns a dict with:
        - status: "healthy" (<70%), "warning" (70-90%), or "critical" (>90%)
        - utilization_pct: Current utilization percentage
        - checked_out: Connections currently in use
        - max_connections: Maximum available connections
        - message: Human-readable health message
        - recommendation: Actionable advice if not healthy

    For NullPool mode, always returns "healthy" since PgBouncer manages the pool.
    """
    stats = get_pool_stats()

    # NullPool / PgBouncer — always healthy from SQLAlchemy's perspective
    if stats.get("pool_type") == "NullPool (PgBouncer)":
        return {
            "status": "healthy",
            "utilization_pct": 0.0,
            "checked_out": 0,
            "max_connections": 0,
            "message": "PgBouncer manages connection pooling externally",
            "recommendation": None,
        }

    if "error" in stats:
        return {
            "status": "critical",
            "utilization_pct": 0.0,
            "checked_out": 0,
            "max_connections": 0,
            "message": f"Cannot read pool stats: {stats['error']}",
            "recommendation": "Investigate database engine initialization",
        }

    utilization_pct = stats["utilization_pct"]
    checked_out = stats["checked_out"]
    max_connections = stats["max_connections"]

    if utilization_pct >= POOL_CRITICAL_THRESHOLD * 100:
        status = "critical"
        message = (
            f"Pool near exhaustion: {checked_out}/{max_connections} connections in use "
            f"({utilization_pct:.0f}%)"
        )
        recommendation = (
            "Immediate action needed. Check for connection leaks (sessions not closed), "
            "long-running queries, or consider enabling PgBouncer."
        )
    elif utilization_pct >= POOL_WARNING_THRESHOLD * 100:
        status = "warning"
        message = (
            f"Pool utilization elevated: {checked_out}/{max_connections} connections in use "
            f"({utilization_pct:.0f}%)"
        )
        recommendation = (
            "Monitor closely. Review slow queries and ensure all sessions are properly closed. "
            "Consider increasing pool_size or max_overflow if sustained."
        )
    else:
        status = "healthy"
        message = (
            f"Pool utilization normal: {checked_out}/{max_connections} connections in use "
            f"({utilization_pct:.0f}%)"
        )
        recommendation = None

    return {
        "status": status,
        "utilization_pct": utilization_pct,
        "checked_out": checked_out,
        "max_connections": max_connections,
        "message": message,
        "recommendation": recommendation,
    }


def _monitor_loop():
    """Background loop that logs pool stats every MONITOR_INTERVAL_SECONDS."""
    global _monitor_running

    logger.info(
        f"DB pool monitor started (interval={MONITOR_INTERVAL_SECONDS}s, "
        f"warn={POOL_WARNING_THRESHOLD*100:.0f}%, crit={POOL_CRITICAL_THRESHOLD*100:.0f}%)"
    )

    while _monitor_running:
        try:
            stats = get_pool_stats()

            # Skip logging for NullPool — no pool to monitor
            if stats.get("pool_type") == "NullPool (PgBouncer)":
                time.sleep(MONITOR_INTERVAL_SECONDS)
                continue

            if "error" in stats:
                logger.error(f"DB pool monitor: failed to collect stats — {stats['error']}")
                time.sleep(MONITOR_INTERVAL_SECONDS)
                continue

            utilization_pct = stats["utilization_pct"]
            checked_out = stats["checked_out"]
            max_connections = stats["max_connections"]
            checked_in = stats["checked_in"]
            overflow = stats["overflow"]

            log_msg = (
                f"DB pool stats: "
                f"checked_out={checked_out}, checked_in={checked_in}, "
                f"overflow={overflow}, max={max_connections}, "
                f"utilization={utilization_pct:.1f}%"
            )

            if utilization_pct >= POOL_CRITICAL_THRESHOLD * 100:
                logger.critical(
                    f"DB POOL CRITICAL: {checked_out}/{max_connections} connections in use "
                    f"({utilization_pct:.0f}%) — risk of connection exhaustion! {log_msg}"
                )
            elif utilization_pct >= POOL_WARNING_THRESHOLD * 100:
                logger.warning(
                    f"DB pool elevated: {checked_out}/{max_connections} connections in use "
                    f"({utilization_pct:.0f}%). {log_msg}"
                )
            else:
                logger.debug(log_msg)

        except Exception as e:
            logger.exception(f"DB pool monitor iteration failed: {e}")

        # Sleep in short increments so the thread can be stopped quickly
        for _ in range(MONITOR_INTERVAL_SECONDS):
            if not _monitor_running:
                break
            time.sleep(1)

    logger.info("DB pool monitor stopped")


def start_pool_monitor():
    """
    Start the background pool monitoring thread.

    Safe to call multiple times — subsequent calls are no-ops if the monitor
    is already running. The thread is daemonic, so it won't prevent process exit.
    """
    global _monitor_thread, _monitor_running

    if _monitor_running and _monitor_thread and _monitor_thread.is_alive():
        logger.debug("DB pool monitor already running — skipping start")
        return

    _monitor_running = True
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="db-pool-monitor",
        daemon=True,
    )
    _monitor_thread.start()
    logger.info("DB pool monitor thread started")


def stop_pool_monitor():
    """
    Stop the background pool monitoring thread.

    Signals the monitor loop to exit. The thread will stop within
    ~1 second thanks to the short sleep increments.
    """
    global _monitor_running
    _monitor_running = False
    logger.info("DB pool monitor stop requested")
