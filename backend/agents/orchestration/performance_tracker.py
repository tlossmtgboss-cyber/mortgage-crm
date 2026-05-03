"""
Performance Tracking for AI Agents

Tracks and analyzes agent performance including:
- Token usage and cost optimization
- Latency metrics
- Conversion rates
- A/B test results
- Quality scoring

Persistence strategy:
- In-memory dicts for current-session fast lookups
- AgentInvocation table (via SessionLocal) as durable source of truth
- Every log_execution / record_response_metrics call writes to both
- flush_to_db() batch-writes any accumulated in-memory records
- DB queries power historical analysis (get_agent_performance, get_performance_trends, etc.)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from decimal import Decimal
import json
import logging
import os
import uuid
from sqlalchemy import select, func, and_, case, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: synchronous DB writes via SessionLocal
# ---------------------------------------------------------------------------

def _get_sync_session():
    """
    Create a synchronous DB session via SessionLocal.

    Returns None if the import or session creation fails (e.g. no DB configured).
    """
    try:
        from db import SessionLocal
        return SessionLocal()
    except Exception as e:
        logger.debug(f"Could not create sync DB session: {e}")
        return None


def _persist_invocation_sync(
    agent_role: str,
    tool_name: str,
    duration_ms: Optional[int] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    tokens_used: Optional[int] = None,
    cost_estimate: Optional[float] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> bool:
    """
    Write a single AgentInvocation row synchronously.

    Returns True on success, False on failure. Never raises.
    """
    session = _get_sync_session()
    if session is None:
        return False

    try:
        from database.models.agent_metrics import AgentInvocation

        now = datetime.now(timezone.utc)
        invocation = AgentInvocation(
            agent_role=agent_role,
            tool_name=tool_name,
            user_id=user_id,
            organization_id=organization_id,
            duration_ms=duration_ms,
            status=status,
            error_message=(error_message[:2000] if error_message else None),
            tokens_used=tokens_used,
            cost_estimate=cost_estimate,
            started_at=now,
            completed_at=now,
            created_at=now,
        )
        session.add(invocation)
        session.commit()
        logger.debug(
            f"Persisted AgentInvocation: role={agent_role} tool={tool_name} "
            f"status={status} duration={duration_ms}ms"
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to persist AgentInvocation: {e}")
        try:
            session.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            session.close()
        except Exception:
            pass


class ResponseTimeTracker:
    """
    Lightweight in-memory response time tracker with percentile calculations.

    Maintains a fixed-size circular buffer of recent response times for
    real-time percentile reporting without DB overhead. Thread-safe.

    Usage:
        tracker = get_response_time_tracker()
        tracker.record(1250, intent="pipeline", model="haiku")
        stats = tracker.get_stats()
        # {'p50': 850, 'p90': 2100, 'p99': 5200, 'count': 42, ...}
    """

    _MAX_SAMPLES = 1000  # Keep last 1000 response times

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._times: List[float] = []
        self._by_intent: Dict[str, List[float]] = defaultdict(list)
        self._by_model: Dict[str, List[float]] = defaultdict(list)
        self._total_count = 0

    def record(self, response_time_ms: float, intent: str = "", model: str = "") -> None:
        """Record a response time measurement."""
        with self._lock:
            self._times.append(response_time_ms)
            if len(self._times) > self._MAX_SAMPLES:
                self._times = self._times[-self._MAX_SAMPLES:]
            self._total_count += 1

            if intent:
                bucket = self._by_intent[intent]
                bucket.append(response_time_ms)
                if len(bucket) > 200:
                    self._by_intent[intent] = bucket[-200:]

            if model:
                bucket = self._by_model[model]
                bucket.append(response_time_ms)
                if len(bucket) > 200:
                    self._by_model[model] = bucket[-200:]

    def get_stats(self) -> Dict[str, Any]:
        """Get percentile stats for recent response times."""
        with self._lock:
            if not self._times:
                return {"count": 0, "total_count": 0}

            sorted_times = sorted(self._times)
            n = len(sorted_times)

            def _percentile(pct: float) -> float:
                idx = int(pct / 100.0 * (n - 1))
                return round(sorted_times[idx], 1)

            stats = {
                "count": n,
                "total_count": self._total_count,
                "p50_ms": _percentile(50),
                "p75_ms": _percentile(75),
                "p90_ms": _percentile(90),
                "p95_ms": _percentile(95),
                "p99_ms": _percentile(99),
                "min_ms": round(sorted_times[0], 1),
                "max_ms": round(sorted_times[-1], 1),
                "avg_ms": round(sum(sorted_times) / n, 1),
            }

            # Per-intent breakdown (top 5 by volume)
            intent_stats = {}
            for intent, times in sorted(
                self._by_intent.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:5]:
                st = sorted(times)
                cnt = len(st)
                intent_stats[intent] = {
                    "count": cnt,
                    "p50_ms": round(st[cnt // 2], 1),
                    "p90_ms": round(st[int(0.9 * (cnt - 1))], 1) if cnt > 1 else round(st[0], 1),
                    "avg_ms": round(sum(st) / cnt, 1),
                }
            stats["by_intent"] = intent_stats

            # Per-model breakdown
            model_stats = {}
            for model_name, times in self._by_model.items():
                st = sorted(times)
                cnt = len(st)
                model_stats[model_name] = {
                    "count": cnt,
                    "p50_ms": round(st[cnt // 2], 1),
                    "p90_ms": round(st[int(0.9 * (cnt - 1))], 1) if cnt > 1 else round(st[0], 1),
                    "avg_ms": round(sum(st) / cnt, 1),
                }
            stats["by_model"] = model_stats

            return stats


# Singleton response time tracker
_response_time_tracker: Optional[ResponseTimeTracker] = None


def get_response_time_tracker() -> ResponseTimeTracker:
    """Get the singleton response time tracker."""
    global _response_time_tracker
    if _response_time_tracker is None:
        _response_time_tracker = ResponseTimeTracker()
    return _response_time_tracker


class PerformanceTracker:
    """
    Track and analyze agent performance.

    Provides insights for optimization:
    - Token usage trends
    - Response quality metrics
    - Conversion funnel analysis
    - A/B test evaluation

    Persistence:
    - In-memory lists for fast current-session access
    - AgentInvocation table as durable source of truth (via SessionLocal)
    - Historical query methods read from DB directly
    """

    # Token costs (approximate, update as needed)
    TOKEN_COSTS = {
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},  # per 1K tokens
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5-20251001": {"input": 0.0008, "output": 0.004},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }

    def __init__(self, db_session: Optional[AsyncSession] = None):
        """
        Initialize performance tracker.

        Args:
            db_session: Optional async database session for legacy persistence
                        (agent_executions / conversation_outcomes tables).
                        New DB persistence uses SessionLocal for the
                        agent_invocations table regardless of this parameter.
        """
        self.db_session = db_session
        self._in_memory_executions: deque = deque(maxlen=500)
        self._in_memory_outcomes: deque = deque(maxlen=500)
        self._pending_invocations: List[Dict] = []

    # ------------------------------------------------------------------
    # Existing API — log_execution (backward-compatible)
    # ------------------------------------------------------------------

    async def log_execution(self, data: Dict[str, Any]) -> str:
        """
        Log an agent execution.

        Args:
            data: Execution data including:
                - agent_id: Agent identifier
                - conversation_id: Conversation UUID
                - user_id: User UUID (optional)
                - stage: Conversation stage
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens
                - latency_ms: Response time in milliseconds
                - response: Response text (optional)
                - model_used: AI model used (optional)
                - metadata: Additional metadata (optional)

        Returns:
            Execution ID
        """
        execution_id = str(uuid.uuid4())
        total_tokens = data.get("prompt_tokens", 0) + data.get("completion_tokens", 0)
        latency_ms = data.get("latency_ms", 0)
        model_used = data.get("model_used", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))

        execution = {
            "id": execution_id,
            "agent_id": data.get("agent_id"),
            "conversation_id": data.get("conversation_id"),
            "user_id": data.get("user_id"),
            "stage": data.get("stage", "unknown"),
            "prompt_tokens": data.get("prompt_tokens", 0),
            "completion_tokens": data.get("completion_tokens", 0),
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "model_used": model_used,
            "response_text": data.get("response"),
            "metadata": data.get("metadata", {}),
            "executed_at": datetime.now(timezone.utc),
        }

        # Always store in memory for current-session lookups
        self._in_memory_executions.append(execution)

        # Legacy async persistence (agent_executions table) if session provided
        if self.db_session:
            await self._persist_execution(execution)

        # Persist to agent_invocations via synchronous SessionLocal
        cost = self._estimate_single_cost(
            data.get("prompt_tokens", 0),
            data.get("completion_tokens", 0),
            model_used,
        )
        _persist_invocation_sync(
            agent_role=data.get("agent_id") or "unknown",
            tool_name=data.get("stage") or "execution",
            duration_ms=latency_ms,
            status="success",
            tokens_used=total_tokens,
            cost_estimate=cost,
            user_id=self._safe_int(data.get("user_id")),
        )

        # Log summary
        logger.info(
            f"Execution logged: agent={data.get('agent_id')} "
            f"tokens={total_tokens} "
            f"latency={latency_ms}ms"
        )

        return execution_id

    # ------------------------------------------------------------------
    # Existing API — log_outcome (backward-compatible)
    # ------------------------------------------------------------------

    async def log_outcome(self, data: Dict[str, Any]) -> str:
        """
        Log a conversation outcome.

        Args:
            data: Outcome data including:
                - conversation_id: Conversation UUID
                - agent_id: Agent UUID
                - user_id: User UUID (optional)
                - outcome_type: qualified/booked/rejected/no_response
                - total_messages: Message count
                - qualification_complete: Boolean
                - booking_made: Boolean
                - revenue_generated: Decimal (optional)
                - metrics: Additional metrics dict (optional)

        Returns:
            Outcome ID
        """
        outcome_id = str(uuid.uuid4())
        outcome = {
            "id": outcome_id,
            "conversation_id": data.get("conversation_id"),
            "agent_id": data.get("agent_id"),
            "user_id": data.get("user_id"),
            "outcome_type": data.get("outcome_type", "unknown"),
            "total_messages": data.get("total_messages", 0),
            "agent_messages": data.get("agent_messages", 0),
            "user_messages": data.get("user_messages", 0),
            "qualification_complete": data.get("qualification_complete", False),
            "booking_made": data.get("booking_made", False),
            "revenue_generated": data.get("revenue_generated"),
            "metrics": data.get("metrics", {}),
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
        }

        # Always keep in memory
        self._in_memory_outcomes.append(outcome)

        if self.db_session:
            await self._persist_outcome(outcome)

        # Also persist an invocation record for the outcome event
        _persist_invocation_sync(
            agent_role=data.get("agent_id") or "unknown",
            tool_name=f"outcome_{data.get('outcome_type', 'unknown')}",
            status="success",
            user_id=self._safe_int(data.get("user_id")),
        )

        logger.info(
            f"Outcome logged: agent={data.get('agent_id')} "
            f"type={outcome['outcome_type']} "
            f"booking={outcome['booking_made']}"
        )

        return outcome_id

    # ------------------------------------------------------------------
    # NEW: record_response_metrics — complete interaction metric
    # ------------------------------------------------------------------

    async def record_response_metrics(
        self,
        agent_role: str,
        response_time_ms: int,
        token_count: int,
        intent: str,
        tools_used: List[str],
        success: bool,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record a complete interaction metric.

        Writes to both in-memory cache and the agent_invocations DB table.

        Args:
            agent_role: The AI agent role (e.g. "pipeline_analyst").
            response_time_ms: Wall-clock response time in milliseconds.
            token_count: Total tokens consumed (prompt + completion).
            intent: Detected user intent that triggered this interaction.
            tools_used: List of tool names invoked during the interaction.
            success: Whether the interaction completed successfully.
            user_id: The user who triggered the interaction (optional).
            organization_id: Tenant / organization ID (optional).
            error_message: Error details when success is False (optional).
        """
        now = datetime.now(timezone.utc)
        status = "success" if success else "error"

        # In-memory record
        record = {
            "agent_role": agent_role,
            "response_time_ms": response_time_ms,
            "token_count": token_count,
            "intent": intent,
            "tools_used": tools_used,
            "success": success,
            "error_message": error_message,
            "user_id": user_id,
            "organization_id": organization_id,
            "recorded_at": now,
        }
        self._in_memory_executions.append({
            "id": str(uuid.uuid4()),
            "agent_id": agent_role,
            "stage": intent,
            "total_tokens": token_count,
            "latency_ms": response_time_ms,
            "model_used": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            "executed_at": now,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "metadata": {"tools_used": tools_used, "success": success},
        })

        # Persist one row per tool used (or one aggregate row if no tools)
        tool_name = ", ".join(tools_used) if tools_used else intent
        cost = self._estimate_single_cost(0, 0, None, total_tokens=token_count)

        _persist_invocation_sync(
            agent_role=agent_role,
            tool_name=tool_name[:200],  # fit column width
            duration_ms=response_time_ms,
            status=status,
            error_message=error_message,
            tokens_used=token_count,
            cost_estimate=cost,
            user_id=user_id,
            organization_id=organization_id,
        )

        logger.info(
            f"Response metrics: role={agent_role} intent={intent} "
            f"tools={len(tools_used)} tokens={token_count} "
            f"latency={response_time_ms}ms success={success}"
        )

    # ------------------------------------------------------------------
    # NEW: get_agent_performance — aggregated DB query
    # ------------------------------------------------------------------

    def get_agent_performance(self, agent_role: str, days: int = 30) -> dict:
        """
        Query the agent_invocations table for aggregated performance metrics.

        Args:
            agent_role: The agent role to query.
            days: Lookback window in days.

        Returns:
            Dictionary with total_invocations, success_rate, avg_duration_ms,
            total_tokens, total_cost, top_tools.
        """
        session = _get_sync_session()
        if session is None:
            return self._empty_agent_performance(agent_role, days)

        try:
            from database.models.agent_metrics import AgentInvocation

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            base = (
                session.query(AgentInvocation)
                .filter(
                    AgentInvocation.agent_role == agent_role,
                    AgentInvocation.created_at >= cutoff,
                )
            )

            overall = base.with_entities(
                func.count(AgentInvocation.id).label("total"),
                func.sum(case((AgentInvocation.status == "success", 1), else_=0)).label("successes"),
                func.avg(AgentInvocation.duration_ms).label("avg_duration"),
                func.sum(AgentInvocation.tokens_used).label("total_tokens"),
                func.sum(AgentInvocation.cost_estimate).label("total_cost"),
            ).one()

            total = overall.total or 0
            successes = overall.successes or 0

            # Top tools
            tool_rows = (
                base.with_entities(
                    AgentInvocation.tool_name,
                    func.count(AgentInvocation.id).label("cnt"),
                    func.avg(AgentInvocation.duration_ms).label("avg_dur"),
                )
                .group_by(AgentInvocation.tool_name)
                .order_by(desc("cnt"))
                .limit(10)
                .all()
            )

            top_tools = [
                {
                    "tool_name": row.tool_name,
                    "invocations": row.cnt,
                    "avg_duration_ms": round(float(row.avg_dur or 0), 1),
                }
                for row in tool_rows
            ]

            return {
                "agent_role": agent_role,
                "period_days": days,
                "total_invocations": total,
                "success_rate": round((successes / total) * 100, 2) if total > 0 else 0.0,
                "avg_duration_ms": round(float(overall.avg_duration or 0), 1),
                "total_tokens": int(overall.total_tokens or 0),
                "total_cost_usd": round(float(overall.total_cost or 0), 6),
                "top_tools": top_tools,
            }
        except Exception as e:
            logger.error(f"get_agent_performance failed: {e}")
            return self._empty_agent_performance(agent_role, days)
        finally:
            try:
                session.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # NEW: get_performance_trends — daily averages over time
    # ------------------------------------------------------------------

    def get_performance_trends(self, agent_role: str, days: int = 30) -> dict:
        """
        Return daily aggregated metrics for the given agent role.

        Args:
            agent_role: The agent role to query.
            days: Lookback window in days.

        Returns:
            Dictionary with a list of daily trend records.
        """
        session = _get_sync_session()
        if session is None:
            return {"agent_role": agent_role, "period_days": days, "trends": []}

        try:
            from database.models.agent_metrics import AgentInvocation

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Use func.date() to truncate to day
            day_col = func.date(AgentInvocation.created_at).label("day")

            rows = (
                session.query(
                    day_col,
                    func.count(AgentInvocation.id).label("invocations"),
                    func.avg(AgentInvocation.duration_ms).label("avg_duration"),
                    func.sum(AgentInvocation.tokens_used).label("total_tokens"),
                    func.sum(case((AgentInvocation.status == "success", 1), else_=0)).label("successes"),
                    func.sum(case((AgentInvocation.status != "success", 1), else_=0)).label("errors"),
                )
                .filter(
                    AgentInvocation.agent_role == agent_role,
                    AgentInvocation.created_at >= cutoff,
                )
                .group_by(day_col)
                .order_by(day_col)
                .all()
            )

            trends = []
            for row in rows:
                inv = row.invocations or 0
                succ = row.successes or 0
                trends.append({
                    "date": str(row.day),
                    "invocations": inv,
                    "avg_duration_ms": round(float(row.avg_duration or 0), 1),
                    "total_tokens": int(row.total_tokens or 0),
                    "success_rate": round((succ / inv) * 100, 2) if inv > 0 else 0.0,
                    "errors": int(row.errors or 0),
                })

            return {
                "agent_role": agent_role,
                "period_days": days,
                "trends": trends,
            }
        except Exception as e:
            logger.error(f"get_performance_trends failed: {e}")
            return {"agent_role": agent_role, "period_days": days, "trends": []}
        finally:
            try:
                session.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # NEW: get_slowest_tools
    # ------------------------------------------------------------------

    def get_slowest_tools(self, limit: int = 10) -> list:
        """
        Return tools with the highest average duration across all agents.

        Args:
            limit: Max results to return.

        Returns:
            List of dicts with tool_name, avg_duration_ms, invocations, primary_agent.
        """
        session = _get_sync_session()
        if session is None:
            return []

        try:
            from database.models.agent_metrics import AgentInvocation

            rows = (
                session.query(
                    AgentInvocation.tool_name,
                    func.count(AgentInvocation.id).label("invocations"),
                    func.avg(AgentInvocation.duration_ms).label("avg_duration"),
                    func.max(AgentInvocation.duration_ms).label("max_duration"),
                )
                .filter(AgentInvocation.duration_ms.isnot(None))
                .group_by(AgentInvocation.tool_name)
                .order_by(desc("avg_duration"))
                .limit(limit)
                .all()
            )

            results = []
            for row in rows:
                # Find primary agent role for this tool
                role_row = (
                    session.query(
                        AgentInvocation.agent_role,
                        func.count(AgentInvocation.id).label("cnt"),
                    )
                    .filter(AgentInvocation.tool_name == row.tool_name)
                    .group_by(AgentInvocation.agent_role)
                    .order_by(desc("cnt"))
                    .first()
                )
                results.append({
                    "tool_name": row.tool_name,
                    "avg_duration_ms": round(float(row.avg_duration or 0), 1),
                    "max_duration_ms": int(row.max_duration or 0),
                    "invocations": row.invocations or 0,
                    "primary_agent": role_row.agent_role if role_row else None,
                })

            return results
        except Exception as e:
            logger.error(f"get_slowest_tools failed: {e}")
            return []
        finally:
            try:
                session.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # NEW: get_error_rates — error rate by agent role
    # ------------------------------------------------------------------

    def get_error_rates(self, days: int = 7) -> dict:
        """
        Return error rates grouped by agent role.

        Args:
            days: Lookback window in days.

        Returns:
            Dictionary keyed by agent_role with total, errors, error_rate,
            and top_errors.
        """
        session = _get_sync_session()
        if session is None:
            return {}

        try:
            from database.models.agent_metrics import AgentInvocation

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            rows = (
                session.query(
                    AgentInvocation.agent_role,
                    func.count(AgentInvocation.id).label("total"),
                    func.sum(case((AgentInvocation.status != "success", 1), else_=0)).label("errors"),
                )
                .filter(AgentInvocation.created_at >= cutoff)
                .group_by(AgentInvocation.agent_role)
                .order_by(desc("errors"))
                .all()
            )

            result = {}
            for row in rows:
                total = row.total or 0
                errors = row.errors or 0

                # Top error messages for this role
                err_rows = (
                    session.query(
                        AgentInvocation.error_message,
                        func.count(AgentInvocation.id).label("cnt"),
                    )
                    .filter(
                        AgentInvocation.agent_role == row.agent_role,
                        AgentInvocation.status != "success",
                        AgentInvocation.created_at >= cutoff,
                        AgentInvocation.error_message.isnot(None),
                    )
                    .group_by(AgentInvocation.error_message)
                    .order_by(desc("cnt"))
                    .limit(5)
                    .all()
                )

                top_errors = [
                    {"message": (er.error_message or "")[:200], "count": er.cnt}
                    for er in err_rows
                ]

                result[row.agent_role] = {
                    "total_invocations": total,
                    "errors": errors,
                    "error_rate": round((errors / total) * 100, 2) if total > 0 else 0.0,
                    "top_errors": top_errors,
                }

            return result
        except Exception as e:
            logger.error(f"get_error_rates failed: {e}")
            return {}
        finally:
            try:
                session.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # NEW: flush_to_db — batch-write accumulated in-memory records
    # ------------------------------------------------------------------

    def flush_to_db(self) -> int:
        """
        Batch-write any accumulated in-memory execution records to the
        agent_invocations table.

        Call this periodically (e.g. from the autonomous task executor)
        to ensure data is not lost if the process restarts.

        Returns:
            Number of records successfully flushed.
        """
        if not self._pending_invocations and not self._in_memory_executions:
            return 0

        session = _get_sync_session()
        if session is None:
            logger.warning("flush_to_db: no DB session available, skipping")
            return 0

        flushed = 0
        try:
            from database.models.agent_metrics import AgentInvocation

            # Flush pending invocations (explicit buffer)
            for rec in list(self._pending_invocations):
                try:
                    now = datetime.now(timezone.utc)
                    inv = AgentInvocation(
                        agent_role=rec.get("agent_role", "unknown"),
                        tool_name=rec.get("tool_name", "unknown"),
                        user_id=rec.get("user_id"),
                        organization_id=rec.get("organization_id"),
                        duration_ms=rec.get("duration_ms"),
                        status=rec.get("status", "success"),
                        error_message=rec.get("error_message"),
                        tokens_used=rec.get("tokens_used"),
                        cost_estimate=rec.get("cost_estimate"),
                        started_at=rec.get("started_at", now),
                        completed_at=rec.get("completed_at", now),
                        created_at=now,
                    )
                    session.add(inv)
                    flushed += 1
                except Exception as e:
                    logger.warning(f"flush_to_db: skipping record: {e}")

            # Flush in-memory executions that haven't been written yet
            for exec_rec in list(self._in_memory_executions):
                if exec_rec.get("_flushed"):
                    continue
                try:
                    now = datetime.now(timezone.utc)
                    inv = AgentInvocation(
                        agent_role=exec_rec.get("agent_id", "unknown"),
                        tool_name=exec_rec.get("stage", "execution"),
                        duration_ms=exec_rec.get("latency_ms"),
                        status="success",
                        tokens_used=exec_rec.get("total_tokens"),
                        started_at=exec_rec.get("executed_at", now),
                        completed_at=exec_rec.get("executed_at", now),
                        created_at=now,
                    )
                    session.add(inv)
                    exec_rec["_flushed"] = True
                    flushed += 1
                except Exception as e:
                    logger.warning(f"flush_to_db: skipping execution record: {e}")

            if flushed > 0:
                session.commit()
                self._pending_invocations.clear()
                logger.info(f"flush_to_db: wrote {flushed} records to agent_invocations")

        except Exception as e:
            logger.error(f"flush_to_db failed: {e}")
            try:
                session.rollback()
            except Exception:
                pass
            flushed = 0
        finally:
            try:
                session.close()
            except Exception:
                pass

        return flushed

    # ------------------------------------------------------------------
    # Existing API — get_agent_metrics (backward-compatible)
    # ------------------------------------------------------------------

    async def _fetch_executions_from_db(self, agent_id: str, start_date: datetime) -> List[Dict]:
        """Fetch executions from database."""
        if not self.db_session:
            return []

        try:
            query = text("""
                SELECT conversation_id, agent_id, stage, prompt_tokens, completion_tokens,
                       total_tokens, latency_ms, model_used, created_at
                FROM agent_executions
                WHERE agent_id = :agent_id AND created_at >= :start_date
                ORDER BY created_at DESC
            """)
            result = await self.db_session.execute(query, {
                "agent_id": agent_id,
                "start_date": start_date
            })
            rows = result.fetchall()
            return [
                {
                    "conversation_id": row[0],
                    "agent_id": row[1],
                    "stage": row[2],
                    "prompt_tokens": row[3] or 0,
                    "completion_tokens": row[4] or 0,
                    "total_tokens": row[5] or 0,
                    "latency_ms": row[6] or 0,
                    "model_used": row[7],
                    "executed_at": row[8],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch executions from database: {e}")
            return []

    async def _fetch_outcomes_from_db(self, agent_id: str, start_date: datetime) -> List[Dict]:
        """Fetch outcomes from database."""
        if not self.db_session:
            return []

        try:
            query = text("""
                SELECT conversation_id, agent_id, user_id, outcome_type,
                       total_messages, agent_messages, user_messages,
                       qualification_complete, booking_made, revenue_generated,
                       created_at, completed_at
                FROM conversation_outcomes
                WHERE agent_id = :agent_id AND created_at >= :start_date
                ORDER BY created_at DESC
            """)
            result = await self.db_session.execute(query, {
                "agent_id": agent_id,
                "start_date": start_date
            })
            rows = result.fetchall()
            return [
                {
                    "conversation_id": row[0],
                    "agent_id": row[1],
                    "user_id": row[2],
                    "outcome_type": row[3],
                    "total_messages": row[4] or 0,
                    "agent_messages": row[5] or 0,
                    "user_messages": row[6] or 0,
                    "qualification_complete": row[7],
                    "booking_made": row[8],
                    "revenue_generated": float(row[9]) if row[9] else 0,
                    "created_at": row[10],
                    "completed_at": row[11],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch outcomes from database: {e}")
            return []

    async def get_agent_metrics(
        self,
        agent_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for an agent.

        Args:
            agent_id: Agent identifier
            days: Number of days to analyze

        Returns:
            Dictionary with performance metrics
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Try to fetch from database first, fall back to in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
            outcomes = await self._fetch_outcomes_from_db(agent_id, start_date)
        else:
            executions = []
            outcomes = []

        # Combine with in-memory data
        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])
        outcomes.extend([
            o for o in self._in_memory_outcomes
            if o.get("agent_id") == agent_id and o.get("created_at", datetime.min) >= start_date
        ])

        if not outcomes:
            return self._empty_metrics(agent_id, days)

        # Calculate metrics
        total_convs = len(outcomes)
        qualified = sum(1 for o in outcomes if o.get("qualification_complete"))
        booked = sum(1 for o in outcomes if o.get("booking_made"))
        responded = sum(1 for o in outcomes if o.get("total_messages", 0) > 1)

        # Token metrics
        total_tokens = sum(e.get("total_tokens", 0) for e in executions)
        avg_tokens = total_tokens / len(executions) if executions else 0

        # Latency metrics
        latencies = [e.get("latency_ms", 0) for e in executions if e.get("latency_ms")]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Cost estimation
        total_cost = self._calculate_cost(executions)

        # Revenue
        total_revenue = sum(
            float(o.get("revenue_generated") or 0)
            for o in outcomes
        )

        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_conversations": total_convs,
            "response_rate": round(responded / total_convs * 100, 1) if total_convs > 0 else 0,
            "qualification_rate": round(qualified / total_convs * 100, 1) if total_convs > 0 else 0,
            "booking_rate": round(booked / total_convs * 100, 1) if total_convs > 0 else 0,
            "pull_through_rate": round(booked / qualified * 100, 1) if qualified > 0 else 0,
            "token_metrics": {
                "total_tokens": total_tokens,
                "avg_tokens_per_execution": int(avg_tokens),
                "estimated_cost_usd": round(total_cost, 2),
            },
            "latency_metrics": {
                "avg_latency_ms": int(avg_latency),
                "p95_latency_ms": int(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0),
            },
            "revenue": {
                "total_generated": round(total_revenue, 2),
                "avg_per_booking": round(total_revenue / booked, 2) if booked > 0 else 0,
            },
            "funnel": {
                "conversations": total_convs,
                "responded": responded,
                "qualified": qualified,
                "booked": booked,
            },
        }

    async def get_stage_breakdown(
        self,
        agent_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get performance breakdown by conversation stage.

        Returns metrics for each stage to identify bottlenecks.
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Fetch from database and combine with in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
        else:
            executions = []

        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])

        # Group by stage
        by_stage: Dict[str, List[Dict]] = {}
        for e in executions:
            stage = e.get("stage", "unknown")
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(e)

        breakdown = {}
        for stage, stage_executions in by_stage.items():
            tokens = [e.get("total_tokens", 0) for e in stage_executions]
            latencies = [e.get("latency_ms", 0) for e in stage_executions]

            breakdown[stage] = {
                "count": len(stage_executions),
                "avg_tokens": int(sum(tokens) / len(tokens)) if tokens else 0,
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
                "total_cost": round(self._calculate_cost(stage_executions), 2),
            }

        return {
            "agent_id": agent_id,
            "period_days": days,
            "stages": breakdown,
        }

    async def compare_agents(
        self,
        agent_ids: List[str],
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Compare performance across multiple agents.
        """
        comparison = {}
        for agent_id in agent_ids:
            comparison[agent_id] = await self.get_agent_metrics(agent_id, days)

        return {
            "period_days": days,
            "agents": comparison,
            "best_performer": max(
                comparison.items(),
                key=lambda x: x[1].get("booking_rate", 0)
            )[0] if comparison else None,
        }

    async def get_token_trends(
        self,
        agent_id: str,
        days: int = 30,
        interval: str = "daily"
    ) -> Dict[str, Any]:
        """
        Get token usage trends over time.
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Fetch from database and combine with in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
        else:
            executions = []

        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])

        # Group by day
        by_day: Dict[str, List[Dict]] = {}
        for e in executions:
            day_key = e.get("executed_at", datetime.now(timezone.utc)).strftime("%Y-%m-%d")
            if day_key not in by_day:
                by_day[day_key] = []
            by_day[day_key].append(e)

        trends = []
        for day, day_executions in sorted(by_day.items()):
            tokens = sum(e.get("total_tokens", 0) for e in day_executions)
            trends.append({
                "date": day,
                "total_tokens": tokens,
                "execution_count": len(day_executions),
                "avg_tokens": int(tokens / len(day_executions)) if day_executions else 0,
            })

        return {
            "agent_id": agent_id,
            "period_days": days,
            "trends": trends,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_cost(self, executions: List[Dict]) -> float:
        """Calculate estimated cost for executions"""
        total_cost = 0.0
        for e in executions:
            model = e.get("model_used", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
            costs = self.TOKEN_COSTS.get(model, self.TOKEN_COSTS.get(os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"), self.TOKEN_COSTS["claude-sonnet-4-20250514"]))

            input_cost = (e.get("prompt_tokens", 0) / 1000) * costs["input"]
            output_cost = (e.get("completion_tokens", 0) / 1000) * costs["output"]
            total_cost += input_cost + output_cost

        return total_cost

    def _estimate_single_cost(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: Optional[str] = None,
        total_tokens: Optional[int] = None,
    ) -> float:
        """Estimate cost for a single interaction."""
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        costs = self.TOKEN_COSTS.get(
            model,
            self.TOKEN_COSTS.get("claude-sonnet-4-20250514"),
        )
        if prompt_tokens or completion_tokens:
            return (prompt_tokens / 1000) * costs["input"] + (completion_tokens / 1000) * costs["output"]
        if total_tokens:
            # Assume 70/30 split input/output when we only have total
            input_est = int(total_tokens * 0.7)
            output_est = total_tokens - input_est
            return (input_est / 1000) * costs["input"] + (output_est / 1000) * costs["output"]
        return 0.0

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        """Safely convert a value to int, returning None if not possible."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _empty_metrics(self, agent_id: str, days: int) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_conversations": 0,
            "response_rate": 0,
            "qualification_rate": 0,
            "booking_rate": 0,
            "pull_through_rate": 0,
            "token_metrics": {
                "total_tokens": 0,
                "avg_tokens_per_execution": 0,
                "estimated_cost_usd": 0,
            },
            "latency_metrics": {
                "avg_latency_ms": 0,
                "p95_latency_ms": 0,
            },
            "revenue": {
                "total_generated": 0,
                "avg_per_booking": 0,
            },
            "funnel": {
                "conversations": 0,
                "responded": 0,
                "qualified": 0,
                "booked": 0,
            },
        }

    def _empty_agent_performance(self, agent_role: str, days: int) -> dict:
        """Return empty agent performance structure."""
        return {
            "agent_role": agent_role,
            "period_days": days,
            "total_invocations": 0,
            "success_rate": 0.0,
            "avg_duration_ms": 0.0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "top_tools": [],
        }

    # ------------------------------------------------------------------
    # Legacy async persistence (agent_executions / conversation_outcomes)
    # ------------------------------------------------------------------

    async def _persist_execution(self, execution: Dict) -> None:
        """Persist execution to database using agent_executions table."""
        if not self.db_session:
            return

        try:
            metadata_json = json.dumps(execution.get("metadata", {}))

            # Insert into agent_executions table
            query = text("""
                INSERT INTO agent_executions (
                    conversation_id, agent_id, stage, prompt_tokens, completion_tokens,
                    total_tokens, latency_ms, model_used, response_text, metadata, created_at
                ) VALUES (
                    :conversation_id, :agent_id, :stage, :prompt_tokens, :completion_tokens,
                    :total_tokens, :latency_ms, :model_used, :response_text, :metadata, :created_at
                )
            """)

            await self.db_session.execute(query, {
                "conversation_id": execution.get("conversation_id"),
                "agent_id": execution.get("agent_id"),
                "stage": execution.get("stage", "unknown"),
                "prompt_tokens": execution.get("prompt_tokens", 0),
                "completion_tokens": execution.get("completion_tokens", 0),
                "total_tokens": execution.get("total_tokens", 0),
                "latency_ms": execution.get("latency_ms", 0),
                "model_used": execution.get("model_used"),
                "response_text": execution.get("response_text"),
                "metadata": metadata_json,
                "created_at": execution.get("executed_at", datetime.now(timezone.utc)),
            })
            await self.db_session.commit()

            logger.debug(f"Persisted execution {execution.get('id')} to database")

        except Exception as e:
            logger.error(f"Failed to persist execution to database: {e}")

    async def _persist_outcome(self, outcome: Dict) -> None:
        """Persist outcome to database using conversation_outcomes table."""
        if not self.db_session:
            return

        try:
            metrics_json = json.dumps(outcome.get("metrics", {}))

            query = text("""
                INSERT INTO conversation_outcomes (
                    conversation_id, agent_id, user_id, outcome_type,
                    total_messages, agent_messages, user_messages,
                    qualification_complete, booking_made, revenue_generated,
                    metrics, created_at, completed_at
                ) VALUES (
                    :conversation_id, :agent_id, :user_id, :outcome_type,
                    :total_messages, :agent_messages, :user_messages,
                    :qualification_complete, :booking_made, :revenue_generated,
                    :metrics, :created_at, :completed_at
                )
            """)

            await self.db_session.execute(query, {
                "conversation_id": outcome.get("conversation_id"),
                "agent_id": outcome.get("agent_id"),
                "user_id": outcome.get("user_id"),
                "outcome_type": outcome.get("outcome_type", "unknown"),
                "total_messages": outcome.get("total_messages", 0),
                "agent_messages": outcome.get("agent_messages", 0),
                "user_messages": outcome.get("user_messages", 0),
                "qualification_complete": outcome.get("qualification_complete", False),
                "booking_made": outcome.get("booking_made", False),
                "revenue_generated": outcome.get("revenue_generated"),
                "metrics": metrics_json,
                "created_at": outcome.get("created_at", datetime.now(timezone.utc)),
                "completed_at": outcome.get("completed_at"),
            })
            await self.db_session.commit()

            logger.debug(f"Persisted outcome {outcome.get('id')} to database")

        except Exception as e:
            logger.error(f"Failed to persist outcome to database: {e}")


class ABTestTracker:
    """
    Track A/B test experiments for agent optimization.
    """

    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db_session = db_session
        self._tests: Dict[str, Dict] = {}

    async def create_test(
        self,
        test_name: str,
        agent_id: str,
        variant_a_config: Dict[str, Any],
        variant_b_config: Dict[str, Any],
        traffic_split: float = 0.5
    ) -> str:
        """
        Create a new A/B test.

        Args:
            test_name: Name of the test
            agent_id: Agent to test
            variant_a_config: Configuration for variant A
            variant_b_config: Configuration for variant B
            traffic_split: Percentage of traffic to variant A (0.0-1.0)

        Returns:
            Test ID
        """
        test_id = str(uuid.uuid4())
        self._tests[test_id] = {
            "id": test_id,
            "test_name": test_name,
            "agent_id": agent_id,
            "status": "active",
            "variant_a_config": variant_a_config,
            "variant_b_config": variant_b_config,
            "traffic_split": traffic_split,
            "variant_a_conversations": 0,
            "variant_b_conversations": 0,
            "variant_a_conversions": 0,
            "variant_b_conversions": 0,
            "created_at": datetime.now(timezone.utc),
            "started_at": datetime.now(timezone.utc),
        }

        logger.info(f"A/B test created: {test_name} ({test_id})")
        return test_id

    def get_variant(self, test_id: str) -> str:
        """
        Get which variant to use for a new conversation.

        Returns 'A' or 'B' based on traffic split.
        """
        import random

        test = self._tests.get(test_id)
        if not test or test.get("status") != "active":
            return "A"

        return "A" if random.random() < test["traffic_split"] else "B"

    async def record_result(
        self,
        test_id: str,
        variant: str,
        converted: bool
    ) -> None:
        """Record a test result"""
        test = self._tests.get(test_id)
        if not test:
            return

        if variant == "A":
            test["variant_a_conversations"] += 1
            if converted:
                test["variant_a_conversions"] += 1
        else:
            test["variant_b_conversations"] += 1
            if converted:
                test["variant_b_conversions"] += 1

    async def get_results(self, test_id: str) -> Dict[str, Any]:
        """Get test results with statistical analysis"""
        test = self._tests.get(test_id)
        if not test:
            return {}

        a_convs = test["variant_a_conversations"]
        b_convs = test["variant_b_conversations"]
        a_converted = test["variant_a_conversions"]
        b_converted = test["variant_b_conversions"]

        a_rate = a_converted / a_convs if a_convs > 0 else 0
        b_rate = b_converted / b_convs if b_convs > 0 else 0

        # Simple significance calculation (for proper stats, use scipy)
        min_sample = 100
        is_significant = a_convs >= min_sample and b_convs >= min_sample

        winner = None
        if is_significant:
            if a_rate > b_rate * 1.05:  # 5% lift threshold
                winner = "A"
            elif b_rate > a_rate * 1.05:
                winner = "B"

        return {
            "test_id": test_id,
            "test_name": test["test_name"],
            "status": test["status"],
            "variant_a": {
                "conversations": a_convs,
                "conversions": a_converted,
                "conversion_rate": round(a_rate * 100, 2),
            },
            "variant_b": {
                "conversations": b_convs,
                "conversions": b_converted,
                "conversion_rate": round(b_rate * 100, 2),
            },
            "lift_percent": round((b_rate - a_rate) / a_rate * 100, 2) if a_rate > 0 else 0,
            "is_significant": is_significant,
            "winner": winner,
            "recommendation": self._get_recommendation(winner, is_significant, a_rate, b_rate),
        }

    def _get_recommendation(
        self,
        winner: Optional[str],
        is_significant: bool,
        a_rate: float,
        b_rate: float
    ) -> str:
        """Generate recommendation based on test results"""
        if not is_significant:
            return "Continue testing - insufficient data for significance"

        if winner == "A":
            return f"Variant A wins with {round((a_rate - b_rate) / b_rate * 100, 1)}% lift. Consider rolling out."
        elif winner == "B":
            return f"Variant B wins with {round((b_rate - a_rate) / a_rate * 100, 1)}% lift. Consider rolling out."
        else:
            return "No clear winner - consider testing different variations"

    async def end_test(self, test_id: str) -> None:
        """End an A/B test"""
        test = self._tests.get(test_id)
        if test:
            test["status"] = "completed"
            test["ended_at"] = datetime.now(timezone.utc)
            logger.info(f"A/B test ended: {test['test_name']} ({test_id})")
