"""
Query Timing Middleware (PERF-006)

Tracks SQL query execution times using SQLAlchemy engine events
(before_cursor_execute / after_cursor_execute). Provides:

- WARNING-level logging for queries exceeding SLOW_QUERY_THRESHOLD (default 1s)
- Aggregate statistics: total queries, slow query count, average query time,
  p95 query time, tracked in a thread-safe module-level dict
- Exposed via /health/query-stats admin endpoint (see health_routes.py)

The existing slow query logger in db.py (threshold 500ms) is preserved for
backward compatibility. This module provides richer aggregate tracking with
a higher default threshold (1000ms) suitable for alerting.

Setup
-----
Call ``setup_query_timing(engine)`` once during app startup::

    from middleware.query_timing import setup_query_timing
    from db import engine
    setup_query_timing(engine)

The module is safe to import before the engine exists; listeners are
attached lazily when ``setup_query_timing`` is called.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

logger = logging.getLogger("middleware.query_timing")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Queries slower than this threshold are logged at WARNING and counted as slow.
SLOW_QUERY_THRESHOLD_S = float(os.getenv("QUERY_TIMING_SLOW_THRESHOLD_S", "1.0"))

# Maximum number of recent query durations to retain for percentile calculation.
# Keeps memory bounded under sustained traffic (~16 KB at 2000 float64 samples).
_MAX_SAMPLES = 2000

# ---------------------------------------------------------------------------
# Thread-safe aggregate statistics
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_total_queries: int = 0
_slow_query_count: int = 0
_total_time_s: float = 0.0
_samples: deque = deque(maxlen=_MAX_SAMPLES)
_initialized: bool = False


def get_query_stats() -> Dict[str, Any]:
    """Return a snapshot of aggregate query timing statistics.

    Returns:
        dict with keys:
            total_queries: int -- total queries tracked since startup
            slow_query_count: int -- queries exceeding SLOW_QUERY_THRESHOLD_S
            slow_query_threshold_s: float -- the configured threshold
            avg_query_ms: float -- average query time in milliseconds
            p95_query_ms: float|None -- 95th percentile query time (ms), or
                None if insufficient samples
            sample_window: int -- number of recent samples retained
            initialized: bool -- whether setup_query_timing() has been called
    """
    with _lock:
        total = _total_queries
        slow = _slow_query_count
        total_time = _total_time_s
        samples_list = sorted(_samples)

    avg_ms = (total_time / total * 1000) if total > 0 else 0.0

    p95_ms: Optional[float] = None
    if len(samples_list) >= 2:
        idx = int(len(samples_list) * 0.95)
        p95_ms = round(samples_list[min(idx, len(samples_list) - 1)] * 1000, 2)

    return {
        "total_queries": total,
        "slow_query_count": slow,
        "slow_query_threshold_s": SLOW_QUERY_THRESHOLD_S,
        "avg_query_ms": round(avg_ms, 2),
        "p95_query_ms": p95_ms,
        "sample_window": len(samples_list),
        "max_sample_window": _MAX_SAMPLES,
        "initialized": _initialized,
    }


def reset_query_stats() -> None:
    """Reset all aggregate statistics. Useful for testing."""
    global _total_queries, _slow_query_count, _total_time_s
    with _lock:
        _total_queries = 0
        _slow_query_count = 0
        _total_time_s = 0.0
        _samples.clear()


# ---------------------------------------------------------------------------
# SQLAlchemy event listeners
# ---------------------------------------------------------------------------

def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query start time on the connection info dict."""
    conn.info.setdefault("_qt_start_times", []).append(time.monotonic())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Compute query duration, update aggregate stats, log if slow."""
    global _total_queries, _slow_query_count, _total_time_s

    start_times = conn.info.get("_qt_start_times")
    if not start_times:
        return
    start = start_times.pop(-1)
    elapsed = time.monotonic() - start

    with _lock:
        _total_queries += 1
        _total_time_s += elapsed
        _samples.append(elapsed)
        if elapsed >= SLOW_QUERY_THRESHOLD_S:
            _slow_query_count += 1

    if elapsed >= SLOW_QUERY_THRESHOLD_S:
        # Truncate very long SQL for logging readability
        truncated = statement[:500] + "..." if len(statement) > 500 else statement
        logger.warning(
            "Slow query (%.1fms > %.0fms threshold): %s",
            elapsed * 1000,
            SLOW_QUERY_THRESHOLD_S * 1000,
            truncated,
        )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_query_timing(engine) -> None:
    """Attach query timing event listeners to the given SQLAlchemy engine.

    Safe to call multiple times; subsequent calls are no-ops.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    global _initialized
    if _initialized:
        logger.debug("Query timing already initialized -- skipping")
        return

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine, "after_cursor_execute", _after_cursor_execute)
    _initialized = True
    logger.info(
        "Query timing middleware initialized (slow threshold=%.1fs, sample window=%d)",
        SLOW_QUERY_THRESHOLD_S,
        _MAX_SAMPLES,
    )
