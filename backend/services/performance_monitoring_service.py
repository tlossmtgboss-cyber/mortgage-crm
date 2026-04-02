"""
Performance Monitoring Service
==============================

Enterprise Readiness Domain 6: Performance & Load Testing

Provides:
1. AI token budget tracking and enforcement (Check 6.13)
2. Database deadlock monitoring via pg_stat_activity (Check 6.8)
3. Webhook throughput metrics (Check 6.9)
4. Performance baseline documentation and validation (Checks 6.1-6.4)
5. AI concurrent capacity tracking (Check 6.14)

Usage:
    from services.performance_monitoring_service import perf_monitor

    # Track token usage per LLM call
    perf_monitor.track_token_usage(
        model="claude-3-haiku", tokens_in=500, tokens_out=1200,
        duration_ms=1500, org_id=1, call_type="extraction",
    )

    # Check deadlocks
    deadlocks = await perf_monitor.check_deadlocks(db)

    # Get webhook throughput
    throughput = perf_monitor.get_webhook_throughput(window_seconds=60)

    # Validate against performance baselines
    report = perf_monitor.get_performance_report()
"""

import os
import time
import logging
import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Deque
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# Performance Baselines (Documented Thresholds)
# =============================================================================

PERFORMANCE_BASELINES = {
    "api": {
        "read_p95_ms": 500,
        "write_p95_ms": 1000,
        "read_p99_ms": 2000,
        "write_p99_ms": 3000,
        "error_rate_pct": 0.1,
        "description": "API response time targets under 100 concurrent users",
    },
    "database": {
        "query_p95_ms": 1000,
        "connection_pool_max_pct": 85,
        "deadlock_tolerance": 0,
        "description": "Database query and connection pool targets",
    },
    "ai_agent": {
        "response_latency_p95_ms": 5000,
        "token_budget_per_query": 18000,
        "token_budget_warning": 12000,
        "concurrent_capacity": 50,
        "description": "AI agent performance targets",
    },
    "webhook": {
        "processing_throughput_per_min": 1000,
        "delivery_p95_ms": 5000,
        "delivery_success_rate_pct": 99.0,
        "description": "Webhook processing and delivery targets",
    },
    "background_worker": {
        "queue_drain_sla_seconds": 300,
        "webhook_batch_throughput_per_min": 60,
        "sync_completion_sla_seconds": 600,
        "description": "Background worker processing targets",
    },
}


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class TokenUsageRecord:
    """Single LLM token usage record."""
    timestamp: float
    model: str
    tokens_in: int
    tokens_out: int
    total_tokens: int
    duration_ms: float
    org_id: Optional[int] = None
    call_type: str = "extraction"
    budget_exceeded: bool = False


@dataclass
class WebhookEvent:
    """Single webhook processing event."""
    timestamp: float
    provider: str
    event_type: str
    duration_ms: float
    success: bool
    status_code: Optional[int] = None


@dataclass
class DeadlockInfo:
    """Deadlock detection result."""
    pid: int
    blocked_by_pid: Optional[int]
    query: str
    wait_event_type: Optional[str]
    state: str
    duration_seconds: float


# =============================================================================
# Performance Monitoring Service
# =============================================================================

class PerformanceMonitoringService:
    """
    Central performance monitoring for enterprise readiness.

    Tracks token budgets, deadlocks, webhook throughput, and validates
    against documented performance baselines.
    """

    # Token budget configuration
    TOKEN_BUDGET_PER_QUERY = 18_000       # Max tokens per single AI query
    TOKEN_BUDGET_WARNING = 12_000          # Warning threshold
    TOKEN_BUDGET_PER_ORG_HOURLY = 500_000  # Max tokens per org per hour
    MAX_CONCURRENT_AI_REQUESTS = 50        # Max simultaneous AI requests

    # Monitoring window sizes
    TOKEN_HISTORY_SIZE = 10_000
    WEBHOOK_HISTORY_SIZE = 10_000

    def __init__(self):
        self._token_history: Deque[TokenUsageRecord] = deque(maxlen=self.TOKEN_HISTORY_SIZE)
        self._webhook_history: Deque[WebhookEvent] = deque(maxlen=self.WEBHOOK_HISTORY_SIZE)
        self._active_ai_requests: int = 0
        self._ai_request_lock = None  # Lazy init for async lock
        self._org_token_usage: Dict[int, Deque] = {}  # org_id -> deque of (timestamp, tokens)

    def _get_lock(self):
        if self._ai_request_lock is None:
            self._ai_request_lock = asyncio.Lock()
        return self._ai_request_lock

    # =========================================================================
    # Token Budget Tracking (Check 6.13)
    # =========================================================================

    def track_token_usage(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: float,
        org_id: Optional[int] = None,
        call_type: str = "extraction",
    ) -> TokenUsageRecord:
        """
        Record token usage for an LLM call.
        Returns the record with budget_exceeded flag set if over limit.
        """
        total = tokens_in + tokens_out
        exceeded = total > self.TOKEN_BUDGET_PER_QUERY

        record = TokenUsageRecord(
            timestamp=time.time(),
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            total_tokens=total,
            duration_ms=duration_ms,
            org_id=org_id,
            call_type=call_type,
            budget_exceeded=exceeded,
        )

        self._token_history.append(record)

        # Track per-org hourly usage
        if org_id is not None:
            if org_id not in self._org_token_usage:
                self._org_token_usage[org_id] = deque(maxlen=5000)
            self._org_token_usage[org_id].append((time.time(), total))

        if exceeded:
            logger.warning(
                f"Token budget exceeded: {total} tokens (limit: {self.TOKEN_BUDGET_PER_QUERY}) "
                f"model={model} org={org_id} type={call_type}"
            )
        elif total > self.TOKEN_BUDGET_WARNING:
            logger.info(
                f"Token usage high: {total} tokens (warning: {self.TOKEN_BUDGET_WARNING}) "
                f"model={model} type={call_type}"
            )

        return record

    def get_token_usage_stats(self, window_seconds: int = 3600) -> Dict[str, Any]:
        """Get token usage statistics for the given time window."""
        cutoff = time.time() - window_seconds
        recent = [r for r in self._token_history if r.timestamp >= cutoff]

        if not recent:
            return {
                "window_seconds": window_seconds,
                "total_requests": 0,
                "total_tokens": 0,
                "avg_tokens_per_request": 0,
                "budget_exceeded_count": 0,
                "by_model": {},
                "by_call_type": {},
            }

        total_tokens = sum(r.total_tokens for r in recent)
        by_model: Dict[str, Dict] = {}
        by_type: Dict[str, Dict] = {}

        for r in recent:
            # By model
            if r.model not in by_model:
                by_model[r.model] = {"requests": 0, "tokens": 0, "avg_duration_ms": 0, "durations": []}
            by_model[r.model]["requests"] += 1
            by_model[r.model]["tokens"] += r.total_tokens
            by_model[r.model]["durations"].append(r.duration_ms)

            # By call type
            if r.call_type not in by_type:
                by_type[r.call_type] = {"requests": 0, "tokens": 0}
            by_type[r.call_type]["requests"] += 1
            by_type[r.call_type]["tokens"] += r.total_tokens

        # Calculate averages
        for model_stats in by_model.values():
            durations = model_stats.pop("durations")
            model_stats["avg_duration_ms"] = round(sum(durations) / len(durations), 1) if durations else 0

        return {
            "window_seconds": window_seconds,
            "total_requests": len(recent),
            "total_tokens": total_tokens,
            "avg_tokens_per_request": round(total_tokens / len(recent)) if recent else 0,
            "budget_exceeded_count": sum(1 for r in recent if r.budget_exceeded),
            "budget_limit": self.TOKEN_BUDGET_PER_QUERY,
            "budget_warning": self.TOKEN_BUDGET_WARNING,
            "by_model": by_model,
            "by_call_type": by_type,
        }

    def get_org_hourly_usage(self, org_id: int) -> Dict[str, Any]:
        """Get hourly token usage for an organization."""
        history = self._org_token_usage.get(org_id, deque())
        cutoff = time.time() - 3600
        recent = [(ts, tokens) for ts, tokens in history if ts >= cutoff]
        total = sum(tokens for _, tokens in recent)

        return {
            "org_id": org_id,
            "hourly_tokens": total,
            "hourly_limit": self.TOKEN_BUDGET_PER_ORG_HOURLY,
            "usage_pct": round((total / self.TOKEN_BUDGET_PER_ORG_HOURLY) * 100, 1),
            "requests_count": len(recent),
            "limit_exceeded": total > self.TOKEN_BUDGET_PER_ORG_HOURLY,
        }

    # =========================================================================
    # Concurrent AI Capacity Tracking (Check 6.14)
    # =========================================================================

    async def acquire_ai_slot(self) -> bool:
        """
        Acquire a slot for an AI request. Returns False if at capacity.
        Must be paired with release_ai_slot().
        """
        async with self._get_lock():
            if self._active_ai_requests >= self.MAX_CONCURRENT_AI_REQUESTS:
                logger.warning(
                    f"AI capacity reached: {self._active_ai_requests}/{self.MAX_CONCURRENT_AI_REQUESTS}"
                )
                return False
            self._active_ai_requests += 1
            return True

    async def release_ai_slot(self):
        """Release an AI request slot."""
        async with self._get_lock():
            self._active_ai_requests = max(0, self._active_ai_requests - 1)

    def get_ai_capacity(self) -> Dict[str, Any]:
        """Get current AI concurrent capacity status."""
        return {
            "active_requests": self._active_ai_requests,
            "max_capacity": self.MAX_CONCURRENT_AI_REQUESTS,
            "utilization_pct": round(
                (self._active_ai_requests / self.MAX_CONCURRENT_AI_REQUESTS) * 100, 1
            ),
            "available_slots": self.MAX_CONCURRENT_AI_REQUESTS - self._active_ai_requests,
            "status": (
                "available" if self._active_ai_requests < self.MAX_CONCURRENT_AI_REQUESTS * 0.7
                else "high" if self._active_ai_requests < self.MAX_CONCURRENT_AI_REQUESTS * 0.9
                else "at_capacity" if self._active_ai_requests < self.MAX_CONCURRENT_AI_REQUESTS
                else "full"
            ),
        }

    # =========================================================================
    # Deadlock Monitoring (Check 6.8)
    # =========================================================================

    async def check_deadlocks(self, db: Session) -> Dict[str, Any]:
        """
        Check for database deadlocks and blocked queries via pg_stat_activity.
        """
        try:
            # Find blocked queries
            blocked = db.execute(text("""
                SELECT
                    blocked.pid AS blocked_pid,
                    blocked.query AS blocked_query,
                    blocked.wait_event_type,
                    blocked.state,
                    EXTRACT(EPOCH FROM (now() - blocked.query_start)) AS duration_seconds,
                    blocking.pid AS blocking_pid,
                    blocking.query AS blocking_query
                FROM pg_stat_activity blocked
                JOIN pg_locks blocked_locks ON blocked.pid = blocked_locks.pid
                JOIN pg_locks blocking_locks
                    ON blocked_locks.locktype = blocking_locks.locktype
                    AND blocked_locks.database IS NOT DISTINCT FROM blocking_locks.database
                    AND blocked_locks.relation IS NOT DISTINCT FROM blocking_locks.relation
                    AND blocked_locks.page IS NOT DISTINCT FROM blocking_locks.page
                    AND blocked_locks.tuple IS NOT DISTINCT FROM blocking_locks.tuple
                    AND blocked_locks.virtualxid IS NOT DISTINCT FROM blocking_locks.virtualxid
                    AND blocked_locks.transactionid IS NOT DISTINCT FROM blocking_locks.transactionid
                    AND blocked_locks.classid IS NOT DISTINCT FROM blocking_locks.classid
                    AND blocked_locks.objid IS NOT DISTINCT FROM blocking_locks.objid
                    AND blocked_locks.objsubid IS NOT DISTINCT FROM blocking_locks.objsubid
                    AND blocked_locks.pid != blocking_locks.pid
                JOIN pg_stat_activity blocking ON blocking_locks.pid = blocking.pid
                WHERE NOT blocked_locks.granted
                ORDER BY duration_seconds DESC
                LIMIT 20
            """)).fetchall()

            # Find long-running queries (potential deadlock indicators)
            long_running = db.execute(text("""
                SELECT
                    pid,
                    state,
                    wait_event_type,
                    EXTRACT(EPOCH FROM (now() - query_start)) AS duration_seconds,
                    LEFT(query, 200) AS query_preview
                FROM pg_stat_activity
                WHERE state != 'idle'
                    AND query_start IS NOT NULL
                    AND EXTRACT(EPOCH FROM (now() - query_start)) > 30
                ORDER BY duration_seconds DESC
                LIMIT 10
            """)).fetchall()

            deadlocks = []
            for row in blocked:
                deadlocks.append({
                    "blocked_pid": row[0],
                    "blocked_query": row[1][:200] if row[1] else None,
                    "wait_event_type": row[2],
                    "state": row[3],
                    "duration_seconds": round(float(row[4] or 0), 1),
                    "blocking_pid": row[5],
                    "blocking_query": row[6][:200] if row[6] else None,
                })

            long_queries = []
            for row in long_running:
                long_queries.append({
                    "pid": row[0],
                    "state": row[1],
                    "wait_event_type": row[2],
                    "duration_seconds": round(float(row[3] or 0), 1),
                    "query_preview": row[4],
                })

            status = "healthy"
            if deadlocks:
                status = "deadlock_detected"
            elif long_queries:
                status = "long_queries_detected"

            return {
                "status": status,
                "deadlocks": deadlocks,
                "deadlock_count": len(deadlocks),
                "long_running_queries": long_queries,
                "long_running_count": len(long_queries),
                "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
                "baseline": {
                    "deadlock_tolerance": PERFORMANCE_BASELINES["database"]["deadlock_tolerance"],
                    "compliant": len(deadlocks) == 0,
                },
            }

        except Exception as e:
            logger.error(f"Deadlock check failed: {e}")
            return {
                "status": "check_failed",
                "error": str(e),
                "deadlocks": [],
                "deadlock_count": 0,
                "long_running_queries": [],
                "long_running_count": 0,
            }

    # =========================================================================
    # Webhook Throughput Metrics (Check 6.9)
    # =========================================================================

    def track_webhook(
        self,
        provider: str,
        event_type: str,
        duration_ms: float,
        success: bool,
        status_code: Optional[int] = None,
    ):
        """Track a webhook processing event."""
        self._webhook_history.append(WebhookEvent(
            timestamp=time.time(),
            provider=provider,
            event_type=event_type,
            duration_ms=duration_ms,
            success=success,
            status_code=status_code,
        ))

    def get_webhook_throughput(self, window_seconds: int = 60) -> Dict[str, Any]:
        """Get webhook throughput metrics for the given time window."""
        cutoff = time.time() - window_seconds
        recent = [e for e in self._webhook_history if e.timestamp >= cutoff]

        if not recent:
            return {
                "window_seconds": window_seconds,
                "total_processed": 0,
                "throughput_per_min": 0,
                "success_rate_pct": 100.0,
                "avg_duration_ms": 0,
                "by_provider": {},
            }

        successes = sum(1 for e in recent if e.success)
        durations = [e.duration_ms for e in recent]

        by_provider: Dict[str, Dict] = {}
        for e in recent:
            if e.provider not in by_provider:
                by_provider[e.provider] = {"processed": 0, "success": 0, "durations": []}
            by_provider[e.provider]["processed"] += 1
            if e.success:
                by_provider[e.provider]["success"] += 1
            by_provider[e.provider]["durations"].append(e.duration_ms)

        # Finalize provider stats
        for provider, stats in by_provider.items():
            d = stats.pop("durations")
            stats["avg_duration_ms"] = round(sum(d) / len(d), 1) if d else 0
            stats["success_rate_pct"] = round((stats["success"] / stats["processed"]) * 100, 1)

        throughput_per_min = len(recent) * (60 / window_seconds)

        return {
            "window_seconds": window_seconds,
            "total_processed": len(recent),
            "throughput_per_min": round(throughput_per_min, 1),
            "success_rate_pct": round((successes / len(recent)) * 100, 1),
            "avg_duration_ms": round(sum(durations) / len(durations), 1),
            "p95_duration_ms": round(sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0], 1),
            "by_provider": by_provider,
            "baseline": {
                "target_throughput_per_min": PERFORMANCE_BASELINES["webhook"]["processing_throughput_per_min"],
                "target_success_rate_pct": PERFORMANCE_BASELINES["webhook"]["delivery_success_rate_pct"],
            },
        }

    # =========================================================================
    # Performance Report (All Baselines)
    # =========================================================================

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Get comprehensive performance report comparing current metrics to baselines.
        """
        token_stats = self.get_token_usage_stats(window_seconds=3600)
        webhook_stats = self.get_webhook_throughput(window_seconds=60)
        ai_capacity = self.get_ai_capacity()

        # Determine overall health
        issues = []
        if token_stats["budget_exceeded_count"] > 0:
            issues.append(f"{token_stats['budget_exceeded_count']} requests exceeded token budget")
        if webhook_stats["success_rate_pct"] < 99.0 and webhook_stats["total_processed"] > 0:
            issues.append(f"Webhook success rate {webhook_stats['success_rate_pct']}% below 99% target")
        if ai_capacity["status"] in ("at_capacity", "full"):
            issues.append(f"AI capacity {ai_capacity['status']}: {ai_capacity['active_requests']}/{ai_capacity['max_capacity']}")

        return {
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
            "overall_status": "degraded" if issues else "healthy",
            "issues": issues,
            "baselines": PERFORMANCE_BASELINES,
            "current_metrics": {
                "token_usage": token_stats,
                "webhook_throughput": webhook_stats,
                "ai_capacity": ai_capacity,
            },
        }


# =============================================================================
# Singleton Instance
# =============================================================================

perf_monitor = PerformanceMonitoringService()
