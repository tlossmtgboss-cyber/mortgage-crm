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
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
