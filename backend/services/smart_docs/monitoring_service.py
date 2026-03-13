"""
Smart Docs Monitoring Service

Production observability for the Smart Docs V2 subsystem. Provides:
- System health checks (AI circuit breakers, DB, queues)
- Processing metrics (throughput, latency, cost)
- SLA compliance tracking with configurable targets
- AI cost reporting with projections
- Error aggregation and circuit breaker trip history

Uses in-memory sliding-window metrics collection (MetricsCollector) that
can optionally push to DataDog or other backends.

Usage:
    from services.smart_docs.monitoring_service import get_monitoring_service

    svc = get_monitoring_service()

    # Record a metric from any service
    svc.record_operation("classification", duration_ms=245, success=True, org_id=1)

    # Query health
    health = svc.get_system_health(db)

    # Query SLA compliance
    sla = svc.get_sla_metrics(db, org_id=1, hours=24)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


# =============================================================================
# SLA TARGETS (operation -> max seconds)
# =============================================================================

SLA_TARGETS = {
    "classification": 30.0,        # < 30 seconds
    "review": 120.0,               # < 2 minutes
    "followup_send": 3600.0,       # < 1 hour after trigger
    "income_calculation": 300.0,   # < 5 minutes
    "ocr": 60.0,                   # < 1 minute
    "bank_analysis": 120.0,        # < 2 minutes
}

# Operation cost estimates (USD) for cost projection
OPERATION_COST_ESTIMATES = {
    "classification": 0.05,
    "review": 0.15,
    "ocr": 0.10,
    "income_calculation": 0.08,
    "bank_analysis": 0.15,
    "extraction": 0.12,
    "cross_validate": 0.10,
}


# =============================================================================
# METRICS COLLECTOR — In-Memory Sliding Window
# =============================================================================

@dataclass
class _MetricEntry:
    """A single metric data point."""
    timestamp: float          # time.monotonic()
    wall_time: float          # time.time() for human-readable output
    operation: str
    duration_ms: float
    success: bool
    org_id: Optional[int]
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    In-memory metrics aggregator with sliding window counters.

    Keeps up to 48 hours of data points (auto-cleaned). Provides:
    - Operation counters (success/failure)
    - Latency histograms (p50, p90, p99)
    - Gauge-style queue depth tracking
    - Per-org breakdown
    """

    def __init__(self, retention_hours: int = 48, cleanup_interval: int = 300):
        self._entries: Deque[_MetricEntry] = deque()
        self._lock = threading.Lock()
        self._retention_seconds = retention_hours * 3600
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.monotonic()

        # Gauge values (point-in-time, not windowed)
        self._gauges: Dict[str, float] = {}

        # Circuit breaker trip log
        self._circuit_trips: Deque[Dict[str, Any]] = deque(maxlen=100)

        # Error log (last N errors for reporting)
        self._errors: Deque[Dict[str, Any]] = deque(maxlen=500)

    def record(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        org_id: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a metric data point."""
        entry = _MetricEntry(
            timestamp=time.monotonic(),
            wall_time=time.time(),
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            org_id=org_id,
            tags=tags or {},
        )
        with self._lock:
            self._entries.append(entry)
            self._maybe_cleanup()

    def record_error(
        self,
        operation: str,
        error_type: str,
        error_message: str,
        org_id: Optional[int] = None,
    ) -> None:
        """Record an error event."""
        with self._lock:
            self._errors.append({
                "timestamp": time.time(),
                "operation": operation,
                "error_type": error_type,
                "error_message": error_message[:500],
                "org_id": org_id,
            })

    def record_circuit_trip(
        self,
        service_name: str,
        new_state: str,
    ) -> None:
        """Record a circuit breaker state change."""
        with self._lock:
            self._circuit_trips.append({
                "timestamp": time.time(),
                "service": service_name,
                "new_state": new_state,
            })

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value (point-in-time metric like queue depth)."""
        with self._lock:
            self._gauges[name] = value

    def get_gauge(self, name: str) -> float:
        """Get a gauge value."""
        with self._lock:
            return self._gauges.get(name, 0.0)

    def get_entries(
        self,
        hours: int = 24,
        operation: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> List[_MetricEntry]:
        """Get metric entries within a time window, with optional filters."""
        cutoff = time.monotonic() - (hours * 3600)
        with self._lock:
            entries = [
                e for e in self._entries
                if e.timestamp > cutoff
                and (operation is None or e.operation == operation)
                and (org_id is None or e.org_id == org_id)
            ]
        return entries

    def get_errors(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get error entries within a time window."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            return [e for e in self._errors if e["timestamp"] > cutoff]

    def get_circuit_trips(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get circuit breaker trips within a time window."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            return [t for t in self._circuit_trips if t["timestamp"] > cutoff]

    def compute_percentiles(
        self,
        entries: List[_MetricEntry],
    ) -> Dict[str, float]:
        """Compute latency percentiles from a list of entries."""
        if not entries:
            return {"p50": 0, "p90": 0, "p99": 0, "min": 0, "max": 0, "avg": 0}

        durations = sorted(e.duration_ms for e in entries)
        n = len(durations)

        def percentile(p: float) -> float:
            idx = int(p / 100 * (n - 1))
            return round(durations[idx], 2)

        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p99": percentile(99),
            "min": round(durations[0], 2),
            "max": round(durations[-1], 2),
            "avg": round(sum(durations) / n, 2),
        }

    def _maybe_cleanup(self) -> None:
        """Remove entries older than retention window. Must hold self._lock."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        cutoff = now - self._retention_seconds
        while self._entries and self._entries[0].timestamp < cutoff:
            self._entries.popleft()


# Module-level singleton
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Return the process-wide MetricsCollector singleton."""
    return _collector


# =============================================================================
# MONITORING SERVICE
# =============================================================================

class SmartDocsMonitoringService:
    """
    Unified monitoring service for the Smart Docs V2 subsystem.

    Aggregates data from:
    - MetricsCollector (in-memory operation metrics)
    - AI resilience circuit breakers
    - AI budget tracker
    - Database (queue depths, processing stats)
    """

    def __init__(self, collector: Optional[MetricsCollector] = None):
        self._collector = collector or get_metrics_collector()

    # ------------------------------------------------------------------
    # record_operation — convenience wrapper for services to call
    # ------------------------------------------------------------------

    def record_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        org_id: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a completed operation for metrics tracking."""
        self._collector.record(
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            org_id=org_id,
            tags=tags,
        )
        if not success and tags:
            self._collector.record_error(
                operation=operation,
                error_type=tags.get("error_type", "unknown"),
                error_message=tags.get("error_message", ""),
                org_id=org_id,
            )

    def record_metric(
        self,
        metric_name: str,
        value: float,
        org_id: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a named metric data point (gauge-style or event)."""
        self._collector.record(
            operation=metric_name,
            duration_ms=value,
            success=True,
            org_id=org_id,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # get_system_health
    # ------------------------------------------------------------------

    def get_system_health(self, db: Session) -> Dict[str, Any]:
        """
        Get system health status. Lightweight check suitable for
        load-balancer health probes.

        Returns:
            dict with ai_services, database, queue_depths, error_rates
        """
        health: Dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {},
        }

        # 1. AI circuit breaker status
        try:
            from services.smart_docs.ai_resilience import get_circuit_status
            circuit_data = get_circuit_status()
            breakers = circuit_data.get("circuit_breakers", {})
            any_open = any(
                b.get("state") == "OPEN" for b in breakers.values()
            )
            health["components"]["ai_services"] = {
                "status": "degraded" if any_open else "healthy",
                "circuit_breakers": breakers,
                "total_services": circuit_data.get("total_services", 0),
            }
            if any_open:
                health["status"] = "degraded"
        except Exception as e:
            logger.warning("Health check: AI circuit status unavailable: %s", e)
            health["components"]["ai_services"] = {
                "status": "unknown",
                "error": str(e)[:200],
            }

        # 2. Database connectivity
        try:
            result = db.execute(sa_text("SELECT 1")).scalar()
            health["components"]["database"] = {
                "status": "healthy" if result == 1 else "unhealthy",
            }
        except Exception as e:
            logger.error("Health check: database connectivity failed: %s", e)
            health["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)[:200],
            }
            health["status"] = "unhealthy"

        # 3. Queue depths
        try:
            queue_depths = self._get_queue_depths(db)
            health["components"]["queues"] = {
                "status": "healthy",
                **queue_depths,
            }
            # Flag if any queue is abnormally deep
            if queue_depths.get("pending_classifications", 0) > 100:
                health["components"]["queues"]["status"] = "degraded"
                health["status"] = "degraded"
        except Exception as e:
            logger.warning("Health check: queue depth query failed: %s", e)
            health["components"]["queues"] = {
                "status": "unknown",
                "error": str(e)[:200],
            }

        # 4. Error rates (last hour and last 24h)
        try:
            errors_1h = self._collector.get_errors(hours=1)
            errors_24h = self._collector.get_errors(hours=24)
            health["components"]["error_rates"] = {
                "last_hour": len(errors_1h),
                "last_24h": len(errors_24h),
            }
            if len(errors_1h) > 50:
                health["status"] = "degraded"
        except Exception as e:
            logger.warning("Health check: error rate query failed: %s", e)

        return health

    # ------------------------------------------------------------------
    # get_processing_metrics
    # ------------------------------------------------------------------

    def get_processing_metrics(
        self,
        org_id: Optional[int] = None,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Get processing metrics: throughput, latency, cost, cache hit rate.

        Args:
            org_id: Filter by organization (None for all)
            hours: Lookback window in hours

        Returns:
            dict with operations breakdown, totals, cache stats
        """
        entries = self._collector.get_entries(hours=hours, org_id=org_id)

        # Group by operation
        by_operation: Dict[str, List[_MetricEntry]] = defaultdict(list)
        for e in entries:
            by_operation[e.operation].append(e)

        operations = {}
        total_success = 0
        total_failure = 0

        for op_name, op_entries in by_operation.items():
            successes = [e for e in op_entries if e.success]
            failures = [e for e in op_entries if not e.success]
            total_success += len(successes)
            total_failure += len(failures)

            percentiles = self._collector.compute_percentiles(successes)
            estimated_cost = len(successes) * OPERATION_COST_ESTIMATES.get(op_name, 0.05)

            operations[op_name] = {
                "count": len(op_entries),
                "success": len(successes),
                "failure": len(failures),
                "success_rate": round(
                    len(successes) / len(op_entries) * 100, 1
                ) if op_entries else 0,
                "latency_ms": percentiles,
                "estimated_cost": round(estimated_cost, 4),
            }

        # Cache stats (from the AI budget tracker if available)
        cache_stats = self._get_cache_stats(org_id)

        return {
            "period_hours": hours,
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "operations": len(entries),
                "success": total_success,
                "failure": total_failure,
                "success_rate": round(
                    total_success / len(entries) * 100, 1
                ) if entries else 0,
            },
            "by_operation": operations,
            "cache": cache_stats,
        }

    # ------------------------------------------------------------------
    # get_sla_metrics
    # ------------------------------------------------------------------

    def get_sla_metrics(
        self,
        org_id: int,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Get SLA compliance metrics for each operation type.

        Compares actual processing times against SLA targets defined
        in SLA_TARGETS.

        Returns:
            dict with per-operation SLA compliance percentages
        """
        sla_results = {}

        for operation, target_seconds in SLA_TARGETS.items():
            entries = self._collector.get_entries(
                hours=hours,
                operation=operation,
                org_id=org_id,
            )
            successful = [e for e in entries if e.success]

            if not successful:
                sla_results[operation] = {
                    "target_seconds": target_seconds,
                    "count": 0,
                    "meeting_sla": 0,
                    "compliance_pct": 100.0,  # No data = no violations
                    "avg_seconds": 0,
                    "p90_seconds": 0,
                }
                continue

            target_ms = target_seconds * 1000
            meeting_sla = len([e for e in successful if e.duration_ms <= target_ms])
            compliance_pct = round(meeting_sla / len(successful) * 100, 1)

            percentiles = self._collector.compute_percentiles(successful)

            sla_results[operation] = {
                "target_seconds": target_seconds,
                "count": len(successful),
                "meeting_sla": meeting_sla,
                "breaching_sla": len(successful) - meeting_sla,
                "compliance_pct": compliance_pct,
                "avg_seconds": round(percentiles["avg"] / 1000, 2),
                "p90_seconds": round(percentiles["p90"] / 1000, 2),
                "p99_seconds": round(percentiles["p99"] / 1000, 2),
            }

        # Overall compliance
        total_ops = sum(r["count"] for r in sla_results.values())
        total_meeting = sum(r["meeting_sla"] for r in sla_results.values())
        overall_pct = round(
            total_meeting / total_ops * 100, 1
        ) if total_ops > 0 else 100.0

        return {
            "period_hours": hours,
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_compliance_pct": overall_pct,
            "total_operations": total_ops,
            "total_meeting_sla": total_meeting,
            "by_operation": sla_results,
        }

    # ------------------------------------------------------------------
    # get_ai_cost_report
    # ------------------------------------------------------------------

    def get_ai_cost_report(
        self,
        org_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get AI cost breakdown with projections.

        Returns:
            dict with cost by operation, daily trend, projected monthly,
            top consumers, cache savings estimate
        """
        hours = days * 24
        entries = self._collector.get_entries(hours=hours, org_id=org_id)
        successful = [e for e in entries if e.success]

        # Cost by operation
        cost_by_op: Dict[str, Dict[str, Any]] = {}
        total_cost = 0.0

        for e in successful:
            op = e.operation
            unit_cost = OPERATION_COST_ESTIMATES.get(op, 0.05)
            if op not in cost_by_op:
                cost_by_op[op] = {"count": 0, "cost": 0.0}
            cost_by_op[op]["count"] += 1
            cost_by_op[op]["cost"] += unit_cost
            total_cost += unit_cost

        # Round costs
        for stats in cost_by_op.values():
            stats["cost"] = round(stats["cost"], 4)

        # Daily trend (bucket entries by calendar day)
        daily_trend: Dict[str, float] = defaultdict(float)
        for e in successful:
            day_key = datetime.fromtimestamp(e.wall_time, tz=timezone.utc).strftime("%Y-%m-%d")
            daily_trend[day_key] += OPERATION_COST_ESTIMATES.get(e.operation, 0.05)

        # Sort by date
        sorted_trend = [
            {"date": k, "cost": round(v, 4)}
            for k, v in sorted(daily_trend.items())
        ]

        # Project monthly cost
        if days > 0 and total_cost > 0:
            daily_avg = total_cost / days
            projected_monthly = round(daily_avg * 30, 2)
        else:
            projected_monthly = 0.0

        # Top consumers by org
        top_consumers: Dict[int, float] = defaultdict(float)
        for e in successful:
            if e.org_id is not None:
                top_consumers[e.org_id] += OPERATION_COST_ESTIMATES.get(e.operation, 0.05)

        top_list = sorted(
            [{"org_id": k, "cost": round(v, 4)} for k, v in top_consumers.items()],
            key=lambda x: x["cost"],
            reverse=True,
        )[:10]

        # Cache savings estimate
        cache_stats = self._get_cache_stats(org_id)
        cache_savings = round(
            cache_stats.get("total_hits", 0) * 0.10, 2  # avg cost per cached call
        )

        return {
            "period_days": days,
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_cost": round(total_cost, 4),
            "total_operations": len(successful),
            "projected_monthly_cost": projected_monthly,
            "by_operation": cost_by_op,
            "daily_trend": sorted_trend,
            "top_consumers": top_list,
            "cache_savings_estimate": cache_savings,
        }

    # ------------------------------------------------------------------
    # get_error_report
    # ------------------------------------------------------------------

    def get_error_report(
        self,
        org_id: Optional[int] = None,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Get error report with aggregation by service and type.

        Returns:
            dict with error counts by service, common types, failed
            operations detail, circuit breaker trip history
        """
        errors = self._collector.get_errors(hours=hours)
        if org_id is not None:
            errors = [e for e in errors if e.get("org_id") == org_id]

        # Count by operation (service)
        by_service: Dict[str, int] = defaultdict(int)
        by_type: Dict[str, int] = defaultdict(int)

        for err in errors:
            by_service[err["operation"]] += 1
            by_type[err["error_type"]] += 1

        # Sort by frequency
        sorted_by_service = sorted(
            [{"service": k, "count": v} for k, v in by_service.items()],
            key=lambda x: x["count"],
            reverse=True,
        )
        sorted_by_type = sorted(
            [{"error_type": k, "count": v} for k, v in by_type.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:20]

        # Recent errors (last 20)
        recent = sorted(errors, key=lambda x: x["timestamp"], reverse=True)[:20]
        for err in recent:
            err["time"] = datetime.fromtimestamp(
                err["timestamp"], tz=timezone.utc
            ).isoformat()

        # Circuit breaker trip history
        trips = self._collector.get_circuit_trips(hours=hours)
        for trip in trips:
            trip["time"] = datetime.fromtimestamp(
                trip["timestamp"], tz=timezone.utc
            ).isoformat()

        return {
            "period_hours": hours,
            "org_id": org_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_errors": len(errors),
            "by_service": sorted_by_service,
            "most_common_types": sorted_by_type,
            "recent_errors": recent,
            "circuit_breaker_trips": trips,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_queue_depths(self, db: Session) -> Dict[str, int]:
        """Query current queue depths from the database."""
        depths: Dict[str, int] = {}

        try:
            # Pending classifications (documents uploaded but not yet classified)
            result = db.execute(sa_text("""
                SELECT COUNT(*) FROM smart_documents
                WHERE doc_type IS NULL
                  AND created_at >= NOW() - INTERVAL '7 days'
            """)).scalar()
            depths["pending_classifications"] = result or 0
        except Exception as e:
            logger.debug("Queue depth query (classifications) failed: %s", e)
            depths["pending_classifications"] = 0

        try:
            # Pending reviews
            result = db.execute(sa_text("""
                SELECT COUNT(*) FROM document_requests
                WHERE status = 'pending_review'
                  AND is_active = true
            """)).scalar()
            depths["pending_reviews"] = result or 0
        except Exception as e:
            logger.debug("Queue depth query (reviews) failed: %s", e)
            depths["pending_reviews"] = 0

        try:
            # Pending follow-ups (campaigns with pending events)
            result = db.execute(sa_text("""
                SELECT COUNT(*) FROM followup_campaigns
                WHERE status = 'active'
            """)).scalar()
            depths["active_followups"] = result or 0
        except Exception as e:
            logger.debug("Queue depth query (followups) failed: %s", e)
            depths["active_followups"] = 0

        return depths

    def _get_cache_stats(self, org_id: Optional[int]) -> Dict[str, Any]:
        """Get cache stats from the budget tracker or cache service."""
        try:
            from middleware.ai_cost_tracker import get_ai_budget_tracker
            tracker = get_ai_budget_tracker()
            if org_id is not None:
                usage = tracker.get_usage(org_id, period_hours=24)
                return {
                    "total_calls": usage.get("call_count", 0),
                    "total_cost_24h": usage.get("total_cost", 0),
                    "total_hits": 0,  # Would need cache service DB query
                }
            return {"total_calls": 0, "total_cost_24h": 0, "total_hits": 0}
        except Exception as e:
            logger.debug("Cache stats unavailable: %s", e)
            return {"total_calls": 0, "total_cost_24h": 0, "total_hits": 0}


# =============================================================================
# SINGLETON
# =============================================================================

_service: Optional[SmartDocsMonitoringService] = None


def get_monitoring_service() -> SmartDocsMonitoringService:
    """Get or create the singleton SmartDocsMonitoringService."""
    global _service
    if _service is None:
        _service = SmartDocsMonitoringService()
    return _service
