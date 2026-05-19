"""
Middleware Timing Instrumentation

Non-intrusive timing wrapper for FastAPI middleware. Measures per-request
execution time of each middleware layer and produces aggregate statistics
to identify actual bottlenecks before consolidation.

Enabling
--------
Set the environment variable ``MIDDLEWARE_TIMING=true`` (any truthy value).
The instrumentation is completely inert when the variable is absent or falsy.

Usage
-----
Replace direct ``app.add_middleware(SomeMiddleware, **kw)`` calls with::

    from middleware.timing_instrumentation import wrap_middleware_for_timing

    wrap_middleware_for_timing(app, SomeMiddleware, "some_middleware", **kw)

When timing is enabled, this wraps SomeMiddleware so its ``dispatch`` is
timed.  When disabled (production default), the middleware is added
normally with zero overhead.

The ``TimingAggregatorMiddleware`` should be added as the **outermost**
middleware (added last) so it can collect all timings and emit the
response header::

    from middleware.timing_instrumentation import TimingAggregatorMiddleware

    # ... add all other middleware first ...
    app.add_middleware(TimingAggregatorMiddleware)

Response header (non-production only)::

    X-Middleware-Timing: csrf:0.3ms|rate_limit:1.2ms|auth:4.5ms|total:12.3ms

Warnings are logged for any middleware that exceeds 10 ms on a single
request.  Every 100 requests a p50/p95 summary is logged at INFO level.
"""

from __future__ import annotations

import logging
import os
import statistics
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("middleware.timing")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TIMING_ENABLED: Optional[bool] = None

SLOW_MIDDLEWARE_THRESHOLD_MS = float(
    os.getenv("MIDDLEWARE_TIMING_SLOW_MS", "10")
)

SUMMARY_INTERVAL = int(os.getenv("MIDDLEWARE_TIMING_SUMMARY_INTERVAL", "100"))

# Maximum number of per-middleware timing samples retained for percentile
# computation.  Keeps memory bounded even under sustained traffic.
_MAX_SAMPLES = 2000


def is_timing_enabled() -> bool:
    """Return True when middleware timing instrumentation is active."""
    global _TIMING_ENABLED
    if _TIMING_ENABLED is None:
        raw = os.getenv("MIDDLEWARE_TIMING", "").strip().lower()
        _TIMING_ENABLED = raw in ("1", "true", "yes", "on")
    return _TIMING_ENABLED


# ---------------------------------------------------------------------------
# Request-scoped timing storage
# ---------------------------------------------------------------------------
# Starlette's request.state is per-request and lives on the ASGI scope dict,
# so we store timings there.  Each entry is (name, elapsed_ms).

_STATE_KEY = "_middleware_timings"


def _get_timings(request: Request) -> List[Tuple[str, float]]:
    """Retrieve the timing list from request.state, creating if absent."""
    timings = getattr(request.state, _STATE_KEY, None)
    if timings is None:
        timings = []
        setattr(request.state, _STATE_KEY, timings)
    return timings


def _record_timing(request: Request, name: str, elapsed_ms: float) -> None:
    """Append one middleware timing record to the request."""
    _get_timings(request).append((name, elapsed_ms))


# ---------------------------------------------------------------------------
# Thread-safe aggregate statistics
# ---------------------------------------------------------------------------

class _TimingStats:
    """Accumulates per-middleware timing samples in a thread-safe manner."""

    def __init__(self, max_samples: int = _MAX_SAMPLES) -> None:
        self._lock = threading.Lock()
        # name -> deque of elapsed_ms floats
        self._samples: Dict[str, deque] = {}
        self._request_count = 0
        self._max_samples = max_samples

    def record(self, name: str, elapsed_ms: float) -> None:
        with self._lock:
            if name not in self._samples:
                self._samples[name] = deque(maxlen=self._max_samples)
            self._samples[name].append(elapsed_ms)

    def increment_requests(self) -> int:
        """Increment the global request counter and return the new value."""
        with self._lock:
            self._request_count += 1
            return self._request_count

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        """Return {name: {p50, p95, max, count}} for all tracked middleware."""
        with self._lock:
            result: Dict[str, Dict[str, float]] = {}
            for name, samples in self._samples.items():
                data = list(samples)
                if not data:
                    continue
                data_sorted = sorted(data)
                result[name] = {
                    "p50": round(statistics.median(data_sorted), 3),
                    "p95": round(
                        data_sorted[int(len(data_sorted) * 0.95)] if len(data_sorted) >= 2 else data_sorted[-1],
                        3,
                    ),
                    "max": round(max(data_sorted), 3),
                    "count": len(data_sorted),
                }
            return result


# Module-level singleton
_stats = _TimingStats()


# ---------------------------------------------------------------------------
# MiddlewareTimingWrapper
# ---------------------------------------------------------------------------

class MiddlewareTimingWrapper(BaseHTTPMiddleware):
    """
    Wraps an existing BaseHTTPMiddleware-style dispatch callable and
    measures how long it takes to execute.

    This is NOT meant to be instantiated directly.  Use
    ``wrap_middleware_for_timing()`` which handles the wrapping
    transparently.
    """

    def __init__(self, app, wrapped_dispatch: Callable, wrapped_middleware_name: str):
        super().__init__(app)
        self._wrapped_dispatch = wrapped_dispatch
        self.name = wrapped_middleware_name

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        try:
            response = await self._wrapped_dispatch(request, call_next)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            elapsed_ms = (time.perf_counter() - start) * 1000
            _record_timing(request, self.name, elapsed_ms)
            _stats.record(self.name, elapsed_ms)
            if elapsed_ms > SLOW_MIDDLEWARE_THRESHOLD_MS:
                logger.warning(
                    "Slow middleware (exception path): %s took %.2fms on %s %s",
                    self.name, elapsed_ms, request.method, request.url.path,
                )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        _record_timing(request, self.name, elapsed_ms)
        _stats.record(self.name, elapsed_ms)
        if elapsed_ms > SLOW_MIDDLEWARE_THRESHOLD_MS:
            logger.warning(
                "Slow middleware: %s took %.2fms on %s %s",
                self.name, elapsed_ms, request.method, request.url.path,
            )
        return response


# ---------------------------------------------------------------------------
# TimingAggregatorMiddleware
# ---------------------------------------------------------------------------

class TimingAggregatorMiddleware(BaseHTTPMiddleware):
    """
    Outermost middleware that collects per-middleware timings stored by
    ``MiddlewareTimingWrapper`` instances and:

    - Adds an ``X-Middleware-Timing`` response header (non-production)
    - Logs a WARNING for any single middleware > threshold
    - Periodically logs a p50/p95 summary across all middleware

    Add this LAST (so it executes first in the LIFO stack).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        total_start = time.perf_counter()
        response = await call_next(request)
        total_ms = (time.perf_counter() - total_start) * 1000

        # ---- Build response header ----
        timings = _get_timings(request)

        parts = [f"{name}:{elapsed:.1f}ms" for name, elapsed in timings]
        parts.append(f"total:{total_ms:.1f}ms")
        header_value = "|".join(parts)

        env = os.getenv("ENVIRONMENT", "development").lower()
        if env != "production":
            response.headers["X-Middleware-Timing"] = header_value

        # ---- Periodic summary ----
        count = _stats.increment_requests()
        if count % SUMMARY_INTERVAL == 0:
            snapshot = _stats.snapshot()
            if snapshot:
                lines = ["Middleware timing summary (last %d samples max):" % _MAX_SAMPLES]
                # Sort by p95 descending so the slowest middleware is at the top
                for name, vals in sorted(
                    snapshot.items(), key=lambda kv: kv[1]["p95"], reverse=True
                ):
                    lines.append(
                        f"  {name:30s}  p50={vals['p50']:7.2f}ms  "
                        f"p95={vals['p95']:7.2f}ms  max={vals['max']:7.2f}ms  "
                        f"n={vals['count']}"
                    )
                logger.info("\n".join(lines))

        return response


# ---------------------------------------------------------------------------
# Helper: wrap_middleware_for_timing
# ---------------------------------------------------------------------------

def wrap_middleware_for_timing(
    app,
    middleware_class: Type,
    name: str,
    **kwargs: Any,
) -> None:
    """
    Add *middleware_class* to *app*, optionally wrapped with timing.

    When ``MIDDLEWARE_TIMING=true``:
        The middleware is instantiated normally, but its ``dispatch`` method
        is intercepted by a ``MiddlewareTimingWrapper`` that records
        execution time per request.

    When timing is disabled (the default / production):
        ``app.add_middleware(middleware_class, **kwargs)`` is called with
        zero additional overhead.

    Parameters
    ----------
    app : FastAPI
        The application instance.
    middleware_class : type
        The middleware class to add (must be a BaseHTTPMiddleware subclass
        or compatible Starlette middleware).
    name : str
        Short label used in logs and the ``X-Middleware-Timing`` header,
        e.g. ``"csrf"`` or ``"rate_limit"``.
    **kwargs
        Keyword arguments forwarded to the middleware constructor.
    """
    if not is_timing_enabled():
        app.add_middleware(middleware_class, **kwargs)
        return

    # Strategy: we add the real middleware normally, then layer a timing
    # wrapper on top.  However, Starlette's add_middleware defers
    # instantiation until app startup, so we can't grab the instance's
    # dispatch method directly.
    #
    # Instead, we use a lightweight approach: create a thin subclass that
    # overrides dispatch to time and delegate.  This avoids double
    # wrapping and keeps the ASGI call chain intact.

    class _TimedVariant(middleware_class):  # type: ignore[misc]
        """Auto-generated timed variant of the middleware."""

        async def dispatch(self, request: Request, call_next) -> Response:
            start = time.perf_counter()
            try:
                response = await super().dispatch(request, call_next)
            except Exception as _exc:  # noqa: BLE001
                logger.exception("unhandled exception")
                elapsed_ms = (time.perf_counter() - start) * 1000
                _record_timing(request, name, elapsed_ms)
                _stats.record(name, elapsed_ms)
                if elapsed_ms > SLOW_MIDDLEWARE_THRESHOLD_MS:
                    logger.warning(
                        "Slow middleware (exception): %s took %.2fms on %s %s",
                        name, elapsed_ms, request.method, request.url.path,
                    )
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000
            _record_timing(request, name, elapsed_ms)
            _stats.record(name, elapsed_ms)
            if elapsed_ms > SLOW_MIDDLEWARE_THRESHOLD_MS:
                logger.warning(
                    "Slow middleware: %s took %.2fms on %s %s",
                    name, elapsed_ms, request.method, request.url.path,
                )
            return response

    # Give the dynamic class a readable name for debugging
    _TimedVariant.__name__ = f"Timed_{middleware_class.__name__}"
    _TimedVariant.__qualname__ = f"Timed_{middleware_class.__qualname__}"

    app.add_middleware(_TimedVariant, **kwargs)
    logger.info("Timing enabled for middleware: %s (%s)", name, middleware_class.__name__)


# ---------------------------------------------------------------------------
# Convenience: get current stats snapshot (for diagnostic endpoints)
# ---------------------------------------------------------------------------

def get_timing_stats() -> Dict[str, Dict[str, float]]:
    """
    Return a snapshot of timing statistics for all instrumented middleware.

    Useful for exposing via a ``/debug/middleware-timing`` endpoint::

        @app.get("/debug/middleware-timing")
        async def middleware_timing():
            from middleware.timing_instrumentation import get_timing_stats
            return get_timing_stats()
    """
    return _stats.snapshot()
