"""
Scheduler Metrics Service - In-process metrics collection for enterprise observability.

Collects counters and timing histograms for scheduler operations including
appointment lifecycle events, booking page activity, API latency, and
calendar sync performance.

Thread-safe via threading.Lock. Designed to be exported periodically to
Prometheus, DataDog, or any external metrics collector.

Usage:
    from services.scheduler_metrics_service import scheduler_metrics

    # Record an event
    scheduler_metrics.record_appointment_created("org_123", "consultation")

    # Time an operation
    import time
    start = time.monotonic()
    ...  # operation
    scheduler_metrics.record_api_latency("create_appointment", (time.monotonic() - start) * 1000)

    # Get summary for health-check dashboard
    summary = scheduler_metrics.get_summary()
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrics storage
# ---------------------------------------------------------------------------

@dataclass
class SchedulerMetrics:
    """Collect and report scheduler operational metrics.

    All public methods are thread-safe. Counters are monotonically increasing
    until ``reset()`` is called (typically after an export cycle).
    """

    _counters: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _timings: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _started_at: float = field(default_factory=time.monotonic)

    # -----------------------------------------------------------------------
    # Appointment lifecycle
    # -----------------------------------------------------------------------

    def record_appointment_created(self, org_id: str, appointment_type: str) -> None:
        """Record a new appointment creation."""
        with self._lock:
            self._counters["appointments.created"] += 1
            self._counters[f"appointments.created.org.{org_id}"] += 1
            self._counters[f"appointments.created.type.{appointment_type}"] += 1

    def record_appointment_cancelled(self, org_id: str, reason: str = "unspecified") -> None:
        """Record an appointment cancellation."""
        with self._lock:
            self._counters["appointments.cancelled"] += 1
            self._counters[f"appointments.cancelled.org.{org_id}"] += 1
            self._counters[f"appointments.cancelled.reason.{reason}"] += 1

    def record_appointment_completed(self, org_id: str) -> None:
        """Record an appointment marked as completed."""
        with self._lock:
            self._counters["appointments.completed"] += 1
            self._counters[f"appointments.completed.org.{org_id}"] += 1

    def record_no_show(self, org_id: str) -> None:
        """Record a no-show event."""
        with self._lock:
            self._counters["appointments.no_show"] += 1
            self._counters[f"appointments.no_show.org.{org_id}"] += 1

    def record_appointment_rescheduled(self, org_id: str) -> None:
        """Record a rescheduled appointment."""
        with self._lock:
            self._counters["appointments.rescheduled"] += 1
            self._counters[f"appointments.rescheduled.org.{org_id}"] += 1

    # -----------------------------------------------------------------------
    # Booking page activity
    # -----------------------------------------------------------------------

    def record_booking_page_view(self, slug: str) -> None:
        """Record a public booking page view."""
        with self._lock:
            self._counters["booking.views"] += 1
            self._counters[f"booking.views.slug.{slug}"] += 1

    def record_booking_conversion(self, slug: str) -> None:
        """Record a successful public booking (conversion from page view)."""
        with self._lock:
            self._counters["booking.conversions"] += 1
            self._counters[f"booking.conversions.slug.{slug}"] += 1

    # -----------------------------------------------------------------------
    # Timing measurements
    # -----------------------------------------------------------------------

    def record_api_latency(self, endpoint: str, duration_ms: float) -> None:
        """Record API endpoint latency in milliseconds.

        Keeps the last 1000 samples per endpoint to bound memory usage.
        """
        with self._lock:
            bucket = self._timings[f"api.latency.{endpoint}"]
            bucket.append(duration_ms)
            if len(bucket) > 1000:
                # Trim oldest half to amortize cost
                self._timings[f"api.latency.{endpoint}"] = bucket[500:]

    def record_sync_duration(self, provider: str, duration_ms: float) -> None:
        """Record calendar sync duration (e.g. Google, Outlook)."""
        with self._lock:
            bucket = self._timings[f"sync.duration.{provider}"]
            bucket.append(duration_ms)
            if len(bucket) > 1000:
                self._timings[f"sync.duration.{provider}"] = bucket[500:]

    def record_email_send_duration(self, email_type: str, duration_ms: float) -> None:
        """Record email send latency (confirmation, cancellation, reminder)."""
        with self._lock:
            bucket = self._timings[f"email.duration.{email_type}"]
            bucket.append(duration_ms)
            if len(bucket) > 1000:
                self._timings[f"email.duration.{email_type}"] = bucket[500:]

    # -----------------------------------------------------------------------
    # Error tracking
    # -----------------------------------------------------------------------

    def record_error(self, operation: str) -> None:
        """Record an error for a given operation."""
        with self._lock:
            self._counters["errors"] += 1
            self._counters[f"errors.{operation}"] += 1

    # -----------------------------------------------------------------------
    # Summary and export
    # -----------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Return metrics summary for the health check dashboard.

        Returns a snapshot of all counters and timing statistics. The
        ``uptime_seconds`` field indicates how long since the last reset
        (or process start).
        """
        with self._lock:
            counters_snapshot = dict(self._counters)
            timing_stats = {}
            for key, values in self._timings.items():
                if not values:
                    continue
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                timing_stats[key] = {
                    "count": n,
                    "min_ms": round(sorted_vals[0], 2),
                    "max_ms": round(sorted_vals[-1], 2),
                    "avg_ms": round(sum(sorted_vals) / n, 2),
                    "p50_ms": round(sorted_vals[n // 2], 2),
                    "p95_ms": round(sorted_vals[int(n * 0.95)], 2) if n >= 20 else None,
                    "p99_ms": round(sorted_vals[int(n * 0.99)], 2) if n >= 100 else None,
                }

        # Compute derived metrics outside the lock
        total_views = counters_snapshot.get("booking.views", 0)
        total_conversions = counters_snapshot.get("booking.conversions", 0)
        conversion_rate = (total_conversions / total_views * 100) if total_views > 0 else 0.0

        total_created = counters_snapshot.get("appointments.created", 0)
        total_cancelled = counters_snapshot.get("appointments.cancelled", 0)
        cancellation_rate = (total_cancelled / total_created * 100) if total_created > 0 else 0.0

        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(time.monotonic() - self._started_at, 1),
            "counters": counters_snapshot,
            "timings": timing_stats,
            "derived": {
                "booking_conversion_rate_pct": round(conversion_rate, 2),
                "cancellation_rate_pct": round(cancellation_rate, 2),
                "total_appointments_created": total_created,
                "total_appointments_cancelled": total_cancelled,
                "total_no_shows": counters_snapshot.get("appointments.no_show", 0),
                "total_errors": counters_snapshot.get("errors", 0),
            },
        }

    def get_prometheus_text(self) -> str:
        """Format metrics in Prometheus text exposition format.

        Returns a string suitable for scraping by a Prometheus server.
        Each counter becomes a ``# TYPE ... counter`` block and each
        timing bucket becomes a ``# TYPE ... summary`` block with
        quantiles.
        """
        lines: List[str] = []

        with self._lock:
            counters_snapshot = dict(self._counters)
            timings_snapshot = {k: list(v) for k, v in self._timings.items()}

        # Counters
        for key, value in sorted(counters_snapshot.items()):
            prom_name = f"scheduler_{key.replace('.', '_').replace('-', '_')}"
            lines.append(f"# TYPE {prom_name} counter")
            lines.append(f"{prom_name} {value}")

        # Timings as summaries
        for key, values in sorted(timings_snapshot.items()):
            if not values:
                continue
            prom_name = f"scheduler_{key.replace('.', '_').replace('-', '_')}"
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            lines.append(f"# TYPE {prom_name} summary")
            lines.append(f'{prom_name}{{quantile="0.5"}} {sorted_vals[n // 2]:.2f}')
            if n >= 20:
                lines.append(f'{prom_name}{{quantile="0.95"}} {sorted_vals[int(n * 0.95)]:.2f}')
            if n >= 100:
                lines.append(f'{prom_name}{{quantile="0.99"}} {sorted_vals[int(n * 0.99)]:.2f}')
            lines.append(f"{prom_name}_count {n}")
            lines.append(f"{prom_name}_sum {sum(sorted_vals):.2f}")

        # Uptime gauge
        lines.append("# TYPE scheduler_uptime_seconds gauge")
        lines.append(f"scheduler_uptime_seconds {time.monotonic() - self._started_at:.1f}")

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Reset all counters and timings.

        Typically called after metrics have been exported to an external
        system. Resets the uptime clock as well.
        """
        with self._lock:
            self._counters.clear()
            self._timings.clear()
            self._started_at = time.monotonic()
        logger.info("Scheduler metrics reset")


# ---------------------------------------------------------------------------
# Singleton instance -- import and use from anywhere
# ---------------------------------------------------------------------------

scheduler_metrics = SchedulerMetrics()
