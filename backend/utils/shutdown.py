"""
Graceful shutdown handling for the Perennia AI backend.

Tracks in-flight requests and provides coordinated shutdown:
1. Sets a shutdown flag so health checks return 503 (stops new traffic from load balancer)
2. Waits for in-flight requests to drain (with configurable timeout)
3. Closes database connections and external services
4. Logs shutdown metrics

Compatible with uvicorn's signal handling. Uses Python standard library only.
"""

import asyncio
import logging
import signal
import time
import threading
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown state and in-flight request tracking."""

    def __init__(self, drain_timeout: float = 30.0):
        """
        Args:
            drain_timeout: Max seconds to wait for in-flight requests to complete.
        """
        self.drain_timeout = drain_timeout
        self._shutting_down = False
        self._in_flight = 0
        self._lock = threading.Lock()
        self._startup_time: Optional[float] = None
        self._total_requests_served: int = 0

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def in_flight_count(self) -> int:
        with self._lock:
            return self._in_flight

    @property
    def uptime_seconds(self) -> float:
        if self._startup_time is None:
            return 0.0
        return time.monotonic() - self._startup_time

    def record_startup(self) -> None:
        """Record the application startup time."""
        self._startup_time = time.monotonic()

    def increment(self) -> None:
        """Increment in-flight request counter."""
        with self._lock:
            self._in_flight += 1
            self._total_requests_served += 1

    def decrement(self) -> None:
        """Decrement in-flight request counter."""
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def begin_shutdown(self) -> None:
        """Set the shutdown flag. Health checks will start returning 503."""
        self._shutting_down = True
        logger.info(
            "Shutdown initiated — health checks now return 503, "
            f"draining {self.in_flight_count} in-flight requests"
        )

    async def wait_for_drain(self) -> dict:
        """Wait for in-flight requests to complete, up to drain_timeout.

        Returns:
            dict with drain metrics (requests_drained, time_taken, timed_out)
        """
        start = time.monotonic()
        initial_count = self.in_flight_count

        while self.in_flight_count > 0:
            elapsed = time.monotonic() - start
            if elapsed >= self.drain_timeout:
                remaining = self.in_flight_count
                logger.warning(
                    f"Drain timeout ({self.drain_timeout}s) reached with "
                    f"{remaining} requests still in-flight — proceeding with shutdown"
                )
                return {
                    "initial_in_flight": initial_count,
                    "remaining_in_flight": remaining,
                    "time_taken": round(elapsed, 2),
                    "timed_out": True,
                }
            await asyncio.sleep(0.25)

        elapsed = time.monotonic() - start
        logger.info(
            f"All in-flight requests drained in {elapsed:.2f}s "
            f"({initial_count} requests)"
        )
        return {
            "initial_in_flight": initial_count,
            "remaining_in_flight": 0,
            "time_taken": round(elapsed, 2),
            "timed_out": False,
        }

    async def shutdown(
        self,
        close_db_engine=None,
        stop_scheduler=None,
    ) -> dict:
        """Execute the full graceful shutdown sequence.

        Args:
            close_db_engine: callable to dispose the SQLAlchemy engine
            stop_scheduler: callable to stop the APScheduler instance

        Returns:
            dict with shutdown metrics
        """
        shutdown_start = time.monotonic()
        metrics = {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_requests_served": self._total_requests_served,
        }

        # Step 1: Signal shutdown (health -> 503)
        self.begin_shutdown()

        # Step 2: Drain in-flight requests
        drain_metrics = await self.wait_for_drain()
        metrics["drain"] = drain_metrics

        # Step 3: Stop the scheduler (if provided)
        if stop_scheduler:
            try:
                stop_scheduler()
                logger.info("APScheduler stopped")
            except Exception as e:
                logger.warning(f"Error stopping scheduler: {e}")

        # Step 4: Close database connections
        if close_db_engine:
            try:
                close_db_engine()
                logger.info("Database engine disposed")
            except Exception as e:
                logger.warning(f"Error disposing database engine: {e}")

        total_time = time.monotonic() - shutdown_start
        metrics["total_shutdown_time"] = round(total_time, 2)

        logger.info(
            f"Graceful shutdown complete in {total_time:.2f}s — "
            f"served {metrics['total_requests_served']} requests over "
            f"{metrics['uptime_seconds']}s uptime"
        )
        return metrics

    def get_status(self) -> dict:
        """Return current shutdown status for health/diagnostics."""
        return {
            "shutting_down": self._shutting_down,
            "in_flight_requests": self.in_flight_count,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_requests_served": self._total_requests_served,
        }


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware that tracks in-flight requests and rejects new ones during shutdown."""

    def __init__(self, app, shutdown_handler: GracefulShutdown):
        super().__init__(app)
        self.shutdown_handler = shutdown_handler

    async def dispatch(self, request: Request, call_next):
        # During shutdown, reject new requests with 503
        # But always allow health check through so the load balancer sees the 503
        if self.shutdown_handler.is_shutting_down:
            path = request.url.path
            # Let health endpoints through so they can return 503 properly
            if path not in ("/health", "/api/v1/health"):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Server is shutting down"},
                    headers={"Retry-After": "5"},
                )

        self.shutdown_handler.increment()
        try:
            response = await call_next(request)
            return response
        finally:
            self.shutdown_handler.decrement()


def install_signal_handlers(shutdown_handler: GracefulShutdown, loop=None):
    """Install SIGTERM and SIGINT handlers that trigger graceful shutdown.

    Uvicorn installs its own signal handlers, so we cooperate by only setting
    the shutdown flag here. The actual shutdown sequence runs via FastAPI's
    on_event("shutdown") handler.

    Args:
        shutdown_handler: The GracefulShutdown instance
        loop: asyncio event loop (auto-detected if not provided)
    """
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name} — initiating graceful shutdown")
        shutdown_handler.begin_shutdown()

    # Install for SIGTERM (sent by Docker/Railway on deploy) and SIGINT (Ctrl+C)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except (OSError, ValueError) as e:
            # ValueError: signal only works in main thread
            # OSError: can't set signal handler on some platforms
            logger.debug(f"Could not install {sig.name} handler: {e}")
