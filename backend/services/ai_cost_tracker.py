"""
AI Cost Tracker Service — Per-Organization Dollar-Cost Tracking

Maps token counts to dollar costs per model, persists cost records to the
database, and provides cost reporting functions for dashboards and budget
alerts.

Complements the in-memory budget enforcement in
``middleware/ai_cost_tracker.py`` (which gates requests pre-call) by
providing persistent, queryable cost data post-call.

Usage:
    from services.ai_cost_tracker import AICostTracker

    tracker = AICostTracker(db)
    tracker.record_usage(
        org_id=1,
        agent_type="pipeline_analyst",
        model="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=800,
        duration_ms=312,
    )

    today_cost = tracker.get_org_cost_today(org_id=1)
    alert = tracker.check_budget_alert(org_id=1)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Redis helper (lazy import, graceful fallback)
# =============================================================================

def _get_redis_client():
    """Get a Redis client for circuit breaker state caching.

    Returns None if Redis is unavailable — callers must handle gracefully.
    """
    try:
        from services.redis_service import redis_service
        return redis_service.get_client()
    except Exception:
        return None


# =============================================================================
# Model Pricing (per 1M tokens, USD)
# =============================================================================

MODEL_PRICING: Dict[str, Dict[str, Decimal]] = {
    # Anthropic — current models
    "claude-haiku-4-5-20251001": {"input": Decimal("0.80"), "output": Decimal("4.00")},
    "claude-sonnet-4-5-20250514": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-sonnet-4-6": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-sonnet-4-20250514": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-opus-4-6": {"input": Decimal("15.00"), "output": Decimal("75.00")},
    # Legacy models still referenced in some code paths
    "claude-3-5-sonnet-20241022": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-3-5-haiku-20241022": {"input": Decimal("0.80"), "output": Decimal("4.00")},
    # OpenAI (used by some analysis features)
    "gpt-4o": {"input": Decimal("2.50"), "output": Decimal("10.00")},
    "gpt-4o-mini": {"input": Decimal("0.15"), "output": Decimal("0.60")},
}

# Fallback pricing if model not found in the table above
_DEFAULT_PRICING: Dict[str, Decimal] = {
    "input": Decimal("3.00"),
    "output": Decimal("15.00"),
}

# Default daily budget per org (USD)
DEFAULT_DAILY_BUDGET: Decimal = Decimal("50.00")

# Budget alert thresholds (percentage of daily budget)
ALERT_THRESHOLDS = {
    "warning": Decimal("0.75"),    # 75%
    "critical": Decimal("0.90"),   # 90%
    "exceeded": Decimal("1.00"),   # 100%
}


# Agent types that bypass the circuit breaker (safety-critical operations)
CRITICAL_AGENT_TYPES = frozenset({
    "compliance_checker",
    "quality_control",
})

# Circuit breaker Redis key prefix and TTL
_CB_KEY_PREFIX = "ai:circuit:"
_CB_TTL_SECONDS = 86400  # 24 hours


def _get_pricing(model: str) -> Dict[str, Decimal]:
    """Return input/output pricing per 1M tokens for a model."""
    return MODEL_PRICING.get(model, _DEFAULT_PRICING)


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    """Calculate dollar cost from token counts and model pricing.

    Returns the total cost in USD (Decimal, 6 decimal places).
    """
    pricing = _get_pricing(model)
    input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing["input"]
    output_cost = (Decimal(output_tokens) / Decimal("1000000")) * pricing["output"]
    return (input_cost + output_cost).quantize(Decimal("0.000001"))


# =============================================================================
# AICostTracker — Database-backed cost tracking
# =============================================================================

class AICostTracker:
    """
    Persistent AI cost tracker backed by the ``ai_cost_records`` table.

    All public methods accept a ``db: Session`` at construction time (or
    can be constructed fresh per request via FastAPI ``Depends``).

    Parameters
    ----------
    db : Session
        SQLAlchemy database session (RLS-aware from get_db()).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Record usage
    # ------------------------------------------------------------------

    def record_usage(
        self,
        org_id: int,
        agent_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Decimal:
        """Record a single AI API call and persist its cost.

        Parameters
        ----------
        org_id : int
            Organization ID for tenant isolation.
        agent_type : str
            Agent role identifier (e.g. ``"pipeline_analyst"``).
        model : str
            Model identifier (e.g. ``"claude-sonnet-4-6"``).
        input_tokens : int
            Number of input/prompt tokens.
        output_tokens : int
            Number of output/completion tokens.
        duration_ms : int, optional
            Wall-clock latency of the API call.
        user_id : int, optional
            User who triggered the call (None for system-initiated).

        Returns
        -------
        Decimal
            The computed cost in USD.
        """
        cost = calculate_cost(model, input_tokens, output_tokens)

        try:
            self.db.execute(text("""
                INSERT INTO ai_cost_records (
                    id, organization_id, user_id, agent_type, model,
                    input_tokens, output_tokens, cost_usd, duration_ms,
                    created_at
                ) VALUES (
                    gen_random_uuid(), :org_id, :user_id, :agent_type, :model,
                    :input_tokens, :output_tokens, :cost_usd, :duration_ms,
                    NOW()
                )
            """), {
                "org_id": org_id,
                "user_id": user_id,
                "agent_type": agent_type,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": str(cost),
                "duration_ms": duration_ms,
            })
            self.db.commit()

            logger.debug(
                "AI cost recorded: org=%d agent=%s model=%s "
                "tokens=%d/%d cost=$%s",
                org_id, agent_type, model,
                input_tokens, output_tokens, cost,
            )
        except Exception as e:
            logger.error("Failed to record AI cost: %s", e)
            try:
                self.db.rollback()
            except Exception:
                pass

        return cost

    # ------------------------------------------------------------------
    # Cost queries
    # ------------------------------------------------------------------

    def get_org_cost_today(self, org_id: int) -> float:
        """Return total AI cost for an org today (UTC), as a float."""
        try:
            result = self.db.execute(text("""
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM ai_cost_records
                WHERE organization_id = :org_id
                  AND created_at >= CURRENT_DATE
            """), {"org_id": org_id}).scalar()
            return float(result)
        except Exception as e:
            logger.error("Failed to get org cost today: %s", e)
            return 0.0

    def get_org_cost_period(
        self,
        org_id: int,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Return cost breakdown for an org over a date range.

        Returns
        -------
        dict
            Keys: total_cost, total_tokens, request_count, daily_breakdown
        """
        try:
            # Overall totals
            totals = self.db.execute(text("""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                    COUNT(*) AS request_count
                FROM ai_cost_records
                WHERE organization_id = :org_id
                  AND created_at >= :start_date
                  AND created_at < :end_date + INTERVAL '1 day'
            """), {
                "org_id": org_id,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchone()

            # Daily breakdown
            daily_rows = self.db.execute(text("""
                SELECT
                    DATE(created_at) AS day,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE organization_id = :org_id
                  AND created_at >= :start_date
                  AND created_at < :end_date + INTERVAL '1 day'
                GROUP BY DATE(created_at)
                ORDER BY day
            """), {
                "org_id": org_id,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchall()

            return {
                "org_id": org_id,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "total_cost": float(totals[0]),
                "total_tokens": int(totals[1]),
                "request_count": int(totals[2]),
                "daily_breakdown": [
                    {
                        "date": str(row[0]),
                        "cost": float(row[1]),
                        "tokens": int(row[2]),
                        "requests": int(row[3]),
                    }
                    for row in daily_rows
                ],
            }
        except Exception as e:
            logger.error("Failed to get org cost period: %s", e)
            return {
                "org_id": org_id,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "total_cost": 0.0,
                "total_tokens": 0,
                "request_count": 0,
                "daily_breakdown": [],
            }

    def get_cost_by_agent(
        self,
        org_id: int,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """Return cost breakdown by agent type for an org.

        Returns
        -------
        dict
            Keys: org_id, period_days, total_cost, agents (list of dicts)
        """
        try:
            rows = self.db.execute(text("""
                SELECT
                    agent_type,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COUNT(*) AS requests,
                    COALESCE(AVG(duration_ms), 0) AS avg_duration_ms
                FROM ai_cost_records
                WHERE organization_id = :org_id
                  AND created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY agent_type
                ORDER BY cost DESC
            """), {
                "org_id": org_id,
                "period_days": period_days,
            }).fetchall()

            agents = [
                {
                    "agent_type": row[0],
                    "cost": float(row[1]),
                    "input_tokens": int(row[2]),
                    "output_tokens": int(row[3]),
                    "requests": int(row[4]),
                    "avg_duration_ms": int(row[5]),
                }
                for row in rows
            ]

            return {
                "org_id": org_id,
                "period_days": period_days,
                "total_cost": sum(a["cost"] for a in agents),
                "agents": agents,
            }
        except Exception as e:
            logger.error("Failed to get cost by agent: %s", e)
            return {
                "org_id": org_id,
                "period_days": period_days,
                "total_cost": 0.0,
                "agents": [],
            }

    def get_cost_by_model(
        self,
        org_id: int,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """Return cost breakdown by model for an org."""
        try:
            rows = self.db.execute(text("""
                SELECT
                    model,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE organization_id = :org_id
                  AND created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY model
                ORDER BY cost DESC
            """), {
                "org_id": org_id,
                "period_days": period_days,
            }).fetchall()

            models = [
                {
                    "model": row[0],
                    "cost": float(row[1]),
                    "input_tokens": int(row[2]),
                    "output_tokens": int(row[3]),
                    "requests": int(row[4]),
                }
                for row in rows
            ]

            return {
                "org_id": org_id,
                "period_days": period_days,
                "total_cost": sum(m["cost"] for m in models),
                "models": models,
            }
        except Exception as e:
            logger.error("Failed to get cost by model: %s", e)
            return {
                "org_id": org_id,
                "period_days": period_days,
                "total_cost": 0.0,
                "models": [],
            }

    # ------------------------------------------------------------------
    # Budget alerts
    # ------------------------------------------------------------------

    def check_budget_alert(
        self,
        org_id: int,
        daily_budget: Optional[Decimal] = None,
    ) -> Optional[str]:
        """Check if an org is approaching or has exceeded its daily budget.

        Parameters
        ----------
        org_id : int
            Organization ID.
        daily_budget : Decimal, optional
            Override budget. Defaults to DEFAULT_DAILY_BUDGET.

        Returns
        -------
        str or None
            Alert message if threshold breached, else None.
        """
        budget = daily_budget or DEFAULT_DAILY_BUDGET
        spent = Decimal(str(self.get_org_cost_today(org_id)))

        if budget <= 0:
            return None

        usage_pct = spent / budget

        if usage_pct >= ALERT_THRESHOLDS["exceeded"]:
            return (
                f"EXCEEDED: Organization {org_id} has spent "
                f"${spent:.2f} of ${budget:.2f} daily AI budget "
                f"({usage_pct * 100:.0f}%). New AI requests may be throttled."
            )
        elif usage_pct >= ALERT_THRESHOLDS["critical"]:
            return (
                f"CRITICAL: Organization {org_id} has spent "
                f"${spent:.2f} of ${budget:.2f} daily AI budget "
                f"({usage_pct * 100:.0f}%). Approaching limit."
            )
        elif usage_pct >= ALERT_THRESHOLDS["warning"]:
            return (
                f"WARNING: Organization {org_id} has spent "
                f"${spent:.2f} of ${budget:.2f} daily AI budget "
                f"({usage_pct * 100:.0f}%)."
            )

        return None

    # ------------------------------------------------------------------
    # Platform-wide summary (admin only)
    # ------------------------------------------------------------------

    def get_platform_cost_summary(
        self,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """Return platform-wide cost summary across all organizations.

        Returns
        -------
        dict
            Keys: period_days, total_cost, total_requests, total_tokens,
            by_org (top 20), by_model, by_agent, daily_trend
        """
        try:
            # Overall totals
            totals = self.db.execute(text("""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COUNT(*) AS total_requests,
                    COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens
                FROM ai_cost_records
                WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
            """), {"period_days": period_days}).fetchone()

            # Top orgs by cost
            org_rows = self.db.execute(text("""
                SELECT
                    organization_id,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY organization_id
                ORDER BY cost DESC
                LIMIT 20
            """), {"period_days": period_days}).fetchall()

            # By model
            model_rows = self.db.execute(text("""
                SELECT
                    model,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY model
                ORDER BY cost DESC
            """), {"period_days": period_days}).fetchall()

            # By agent type
            agent_rows = self.db.execute(text("""
                SELECT
                    agent_type,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY agent_type
                ORDER BY cost DESC
            """), {"period_days": period_days}).fetchall()

            # Daily trend
            daily_rows = self.db.execute(text("""
                SELECT
                    DATE(created_at) AS day,
                    COALESCE(SUM(cost_usd), 0) AS cost,
                    COUNT(*) AS requests
                FROM ai_cost_records
                WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                GROUP BY DATE(created_at)
                ORDER BY day
            """), {"period_days": period_days}).fetchall()

            return {
                "period_days": period_days,
                "total_cost": float(totals[0]),
                "total_requests": int(totals[1]),
                "total_tokens": int(totals[2]),
                "by_org": [
                    {"organization_id": row[0], "cost": float(row[1]), "requests": int(row[2])}
                    for row in org_rows
                ],
                "by_model": [
                    {"model": row[0], "cost": float(row[1]), "requests": int(row[2])}
                    for row in model_rows
                ],
                "by_agent": [
                    {"agent_type": row[0], "cost": float(row[1]), "requests": int(row[2])}
                    for row in agent_rows
                ],
                "daily_trend": [
                    {"date": str(row[0]), "cost": float(row[1]), "requests": int(row[2])}
                    for row in daily_rows
                ],
            }
        except Exception as e:
            logger.error("Failed to get platform cost summary: %s", e)
            return {
                "period_days": period_days,
                "total_cost": 0.0,
                "total_requests": 0,
                "total_tokens": 0,
                "by_org": [],
                "by_model": [],
                "by_agent": [],
                "daily_trend": [],
            }

    def get_daily_trend(
        self,
        org_id: Optional[int] = None,
        period_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Return daily cost trend for an org or the whole platform.

        Returns
        -------
        list[dict]
            Each dict has: date, cost, input_tokens, output_tokens, requests
        """
        try:
            if org_id is not None:
                rows = self.db.execute(text("""
                    SELECT
                        DATE(created_at) AS day,
                        COALESCE(SUM(cost_usd), 0) AS cost,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COUNT(*) AS requests
                    FROM ai_cost_records
                    WHERE organization_id = :org_id
                      AND created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                    GROUP BY DATE(created_at)
                    ORDER BY day
                """), {"org_id": org_id, "period_days": period_days}).fetchall()
            else:
                rows = self.db.execute(text("""
                    SELECT
                        DATE(created_at) AS day,
                        COALESCE(SUM(cost_usd), 0) AS cost,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COUNT(*) AS requests
                    FROM ai_cost_records
                    WHERE created_at >= CURRENT_DATE - :period_days * INTERVAL '1 day'
                    GROUP BY DATE(created_at)
                    ORDER BY day
                """), {"period_days": period_days}).fetchall()

            return [
                {
                    "date": str(row[0]),
                    "cost": float(row[1]),
                    "input_tokens": int(row[2]),
                    "output_tokens": int(row[3]),
                    "requests": int(row[4]),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error("Failed to get daily trend: %s", e)
            return []

    # ------------------------------------------------------------------
    # Budget status (all orgs)
    # ------------------------------------------------------------------

    def get_all_budget_status(self) -> List[Dict[str, Any]]:
        """Return spend vs budget for all orgs with recent AI usage.

        Joins against organizations table to pull per-org budgets.
        """
        try:
            rows = self.db.execute(text("""
                SELECT
                    acr.organization_id,
                    COALESCE(o.name, 'Org ' || acr.organization_id) AS org_name,
                    COALESCE(SUM(acr.cost_usd), 0) AS spent_today,
                    COALESCE(o.ai_daily_budget_usd, :default_budget) AS daily_budget
                FROM ai_cost_records acr
                LEFT JOIN organizations o ON o.id = acr.organization_id
                WHERE acr.created_at >= CURRENT_DATE
                GROUP BY acr.organization_id, o.name, o.ai_daily_budget_usd
                ORDER BY spent_today DESC
            """), {"default_budget": str(DEFAULT_DAILY_BUDGET)}).fetchall()

            results = []
            for row in rows:
                org_id = int(row[0])
                org_name = str(row[1])
                spent = float(row[2])
                budget = float(row[3])
                pct = (spent / budget * 100) if budget > 0 else 0.0

                # Determine circuit breaker state from cache
                cb_state = _get_circuit_breaker_state(org_id)

                results.append({
                    "organization_id": org_id,
                    "org_name": org_name,
                    "spent_today": round(spent, 2),
                    "daily_budget": round(budget, 2),
                    "usage_pct": round(pct, 1),
                    "circuit_breaker_state": cb_state,
                })

            return results
        except Exception as e:
            logger.error("Failed to get all budget status: %s", e)
            return []

    # ------------------------------------------------------------------
    # Budget alerts log
    # ------------------------------------------------------------------

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent orgs that have crossed budget thresholds today.

        Scans today's cost records and returns any org whose spend has
        crossed warning/critical/exceeded thresholds.
        """
        try:
            rows = self.db.execute(text("""
                SELECT
                    acr.organization_id,
                    COALESCE(o.name, 'Org ' || acr.organization_id) AS org_name,
                    COALESCE(SUM(acr.cost_usd), 0) AS spent_today,
                    COALESCE(o.ai_daily_budget_usd, :default_budget) AS daily_budget
                FROM ai_cost_records acr
                LEFT JOIN organizations o ON o.id = acr.organization_id
                WHERE acr.created_at >= CURRENT_DATE
                GROUP BY acr.organization_id, o.name, o.ai_daily_budget_usd
                HAVING COALESCE(SUM(acr.cost_usd), 0) >=
                    COALESCE(o.ai_daily_budget_usd, :default_budget) * :warning_pct
                ORDER BY COALESCE(SUM(acr.cost_usd), 0) DESC
                LIMIT :limit
            """), {
                "default_budget": str(DEFAULT_DAILY_BUDGET),
                "warning_pct": str(ALERT_THRESHOLDS["warning"]),
                "limit": limit,
            }).fetchall()

            alerts = []
            for row in rows:
                org_id = int(row[0])
                org_name = str(row[1])
                spent = Decimal(str(row[2]))
                budget = Decimal(str(row[3]))
                pct = (spent / budget) if budget > 0 else Decimal("0")

                if pct >= ALERT_THRESHOLDS["exceeded"]:
                    level = "exceeded"
                elif pct >= ALERT_THRESHOLDS["critical"]:
                    level = "critical"
                else:
                    level = "warning"

                alerts.append({
                    "organization_id": org_id,
                    "org_name": org_name,
                    "level": level,
                    "spent_today": float(spent),
                    "daily_budget": float(budget),
                    "usage_pct": round(float(pct * 100), 1),
                    "message": (
                        f"{level.upper()}: {org_name} has spent "
                        f"${spent:.2f} of ${budget:.2f} daily budget "
                        f"({pct * 100:.0f}%)"
                    ),
                })

            return alerts
        except Exception as e:
            logger.error("Failed to get recent alerts: %s", e)
            return []


# =============================================================================
# Circuit Breaker — Per-org AI cost circuit breaker
# =============================================================================

# In-memory fallback when Redis is unavailable
_cb_memory_lock = threading.Lock()
_cb_memory_state: Dict[int, Dict[str, Any]] = {}


def _get_circuit_breaker_state(org_id: int) -> str:
    """Read circuit breaker state from Redis (fast path) or memory fallback.

    Returns one of: "closed", "warning", "critical", "open"
    """
    redis = _get_redis_client()
    key = f"{_CB_KEY_PREFIX}{org_id}"

    if redis is not None:
        try:
            state = redis.get(key)
            if state is not None:
                return state.decode("utf-8") if isinstance(state, bytes) else str(state)
        except Exception as e:
            logger.debug("Redis read failed for circuit breaker state: %s", e)

    # In-memory fallback
    with _cb_memory_lock:
        entry = _cb_memory_state.get(org_id)
        if entry and entry.get("expires_at", 0) > time.time():
            return entry["state"]

    return "closed"


def _set_circuit_breaker_state(org_id: int, state: str) -> None:
    """Write circuit breaker state to Redis + in-memory fallback."""
    redis = _get_redis_client()
    key = f"{_CB_KEY_PREFIX}{org_id}"

    if redis is not None:
        try:
            redis.setex(key, _CB_TTL_SECONDS, state)
        except Exception as e:
            logger.debug("Redis write failed for circuit breaker state: %s", e)

    # Always update in-memory as well (for fast reads and Redis-down fallback)
    with _cb_memory_lock:
        _cb_memory_state[org_id] = {
            "state": state,
            "expires_at": time.time() + _CB_TTL_SECONDS,
        }


def check_circuit_breaker(
    org_id: int,
    db: Session,
    agent_type: Optional[str] = None,
) -> Tuple[bool, str]:
    """Check whether an AI request should be allowed for this org.

    Uses a three-tier threshold system against the org's daily budget:
    - WARNING (75%): log warning, allow request
    - CRITICAL (90%): allow request, signal caller to add warning header
    - EXCEEDED (100%): block request (unless agent is in CRITICAL_AGENT_TYPES)

    Fast path: checks Redis/in-memory cache first. Only queries DB when
    cache indicates closed state to refresh the check.

    Parameters
    ----------
    org_id : int
        Organization ID.
    db : Session
        SQLAlchemy session for budget lookup.
    agent_type : str, optional
        Agent type for critical-agent bypass logic.

    Returns
    -------
    tuple[bool, str]
        (allowed, reason) — allowed=True means request can proceed.
        Reason is one of: "ok", "warning", "critical", "exceeded",
        "exceeded_bypass" (critical agent bypassed the breaker).
    """
    # Fast path: check cached state
    cached_state = _get_circuit_breaker_state(org_id)

    if cached_state == "open":
        # Circuit is open (budget exceeded)
        if agent_type and agent_type in CRITICAL_AGENT_TYPES:
            logger.warning(
                "Circuit breaker OPEN for org=%d but allowing critical agent=%s",
                org_id, agent_type,
            )
            return True, "exceeded_bypass"
        return False, "exceeded"

    # For warning/critical cached states, allow but propagate the state
    if cached_state == "critical":
        return True, "critical"
    if cached_state == "warning":
        return True, "warning"

    # Cached state is "closed" — refresh from DB to catch threshold crossings
    try:
        budget = _get_org_budget(org_id, db)
        if budget is None:
            # NULL budget = unlimited
            return True, "ok"

        spent = _get_org_spent_today(org_id, db)
        budget_dec = Decimal(str(budget))

        if budget_dec <= 0:
            return True, "ok"

        usage_pct = spent / budget_dec

        if usage_pct >= ALERT_THRESHOLDS["exceeded"]:
            _set_circuit_breaker_state(org_id, "open")
            logger.warning(
                "Circuit breaker OPEN: org=%d spent=$%s of $%s budget (%s%%)",
                org_id, spent, budget_dec, round(float(usage_pct * 100)),
            )
            if agent_type and agent_type in CRITICAL_AGENT_TYPES:
                return True, "exceeded_bypass"
            return False, "exceeded"

        elif usage_pct >= ALERT_THRESHOLDS["critical"]:
            _set_circuit_breaker_state(org_id, "critical")
            logger.warning(
                "Circuit breaker CRITICAL: org=%d at %s%% of budget",
                org_id, round(float(usage_pct * 100)),
            )
            return True, "critical"

        elif usage_pct >= ALERT_THRESHOLDS["warning"]:
            _set_circuit_breaker_state(org_id, "warning")
            logger.info(
                "Circuit breaker WARNING: org=%d at %s%% of budget",
                org_id, round(float(usage_pct * 100)),
            )
            return True, "warning"

        return True, "ok"

    except Exception as e:
        logger.error("Circuit breaker check failed for org=%d: %s", org_id, e)
        # Fail open — don't block on transient errors
        return True, "ok"


def reset_circuit_breaker(org_id: int) -> None:
    """Manually reset the circuit breaker for an org (admin action).

    Clears both Redis and in-memory state.
    """
    redis = _get_redis_client()
    key = f"{_CB_KEY_PREFIX}{org_id}"

    if redis is not None:
        try:
            redis.delete(key)
        except Exception as e:
            logger.debug("Redis delete failed for circuit breaker reset: %s", e)

    with _cb_memory_lock:
        _cb_memory_state.pop(org_id, None)

    logger.info("Circuit breaker reset for org=%d", org_id)


def _get_org_budget(org_id: int, db: Session) -> Optional[Decimal]:
    """Fetch the org's daily AI budget from the organizations table.

    Returns None if the org has no budget set (unlimited).
    """
    try:
        result = db.execute(text("""
            SELECT ai_daily_budget_usd
            FROM organizations
            WHERE id = :org_id
        """), {"org_id": org_id}).scalar()
        if result is None:
            return None
        return Decimal(str(result))
    except Exception as e:
        logger.debug("Failed to fetch org budget: %s", e)
        return DEFAULT_DAILY_BUDGET


def _get_org_spent_today(org_id: int, db: Session) -> Decimal:
    """Fetch total AI spend for an org today (UTC)."""
    try:
        result = db.execute(text("""
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM ai_cost_records
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
        """), {"org_id": org_id}).scalar()
        return Decimal(str(result))
    except Exception as e:
        logger.debug("Failed to fetch org spend today: %s", e)
        return Decimal("0")
