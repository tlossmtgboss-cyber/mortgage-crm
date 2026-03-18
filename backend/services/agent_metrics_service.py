"""
Agent Performance Metrics Service

Provides functions to record agent invocations and query aggregate metrics
for the admin dashboard.

Usage:
    from services.agent_metrics_service import record_invocation, get_metrics_summary

    # Record a tool call
    record_invocation(
        db=db,
        agent_role="pipeline_analyst",
        tool_name="get_pipeline_metrics",
        user_id=42,
        org_id=1,
        duration_ms=312,
        status="success",
        tokens=1500,
    )

    # Get dashboard summary
    summary = get_metrics_summary(db, org_id=1, days=30)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, case, cast, String, desc
from sqlalchemy.orm import Session

from database.models.agent_metrics import AgentInvocation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------

def record_invocation(
    db: Session,
    agent_role: str,
    tool_name: str,
    user_id: Optional[int] = None,
    org_id: Optional[int] = None,
    duration_ms: Optional[int] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    tokens: Optional[int] = None,
    cost_estimate: Optional[float] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> AgentInvocation:
    """
    Record a single agent tool invocation.

    This is the primary write entry-point.  Call it after every tool call
    completes (successfully or not).

    Args:
        db: Active SQLAlchemy session (caller is responsible for commit).
        agent_role: The AI agent role (e.g. "pipeline_analyst").
        tool_name: The tool that was invoked (e.g. "get_pipeline_metrics").
        user_id: The user who triggered the invocation (nullable for system calls).
        org_id: Organization / tenant ID.
        duration_ms: Wall-clock milliseconds for the invocation.
        status: One of "success", "error", "timeout".
        error_message: Error details when status != "success".
        tokens: Total tokens consumed (prompt + completion).
        cost_estimate: Estimated cost in USD.
        started_at: Override start time (defaults to now).
        completed_at: Override completion time (defaults to now).

    Returns:
        The persisted AgentInvocation instance.
    """
    now = datetime.now(timezone.utc)
    invocation = AgentInvocation(
        agent_role=agent_role,
        tool_name=tool_name,
        user_id=user_id,
        organization_id=org_id,
        duration_ms=duration_ms,
        status=status,
        error_message=error_message[:2000] if error_message else None,
        tokens_used=tokens,
        cost_estimate=cost_estimate,
        started_at=started_at or now,
        completed_at=completed_at or now,
        created_at=now,
    )
    db.add(invocation)
    try:
        db.flush()  # Assign ID; caller commits
    except Exception as e:
        logger.warning(f"Failed to flush agent invocation record: {e}")
        db.rollback()
        raise
    return invocation


# ---------------------------------------------------------------------------
# Read path — summary
# ---------------------------------------------------------------------------

def get_metrics_summary(
    db: Session,
    org_id: Optional[int] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Return an aggregate metrics summary for the admin dashboard.

    Returns:
        {
            "period_days": int,
            "total_invocations": int,
            "success_rate": float,           # 0-100
            "avg_duration_ms": float,
            "total_tokens": int,
            "total_cost": float,
            "by_agent_role": [ ... ],
            "by_tool": [ ... ],
            "error_distribution": [ ... ],
        }
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(AgentInvocation).filter(AgentInvocation.created_at >= cutoff)
    if org_id is not None:
        base = base.filter(AgentInvocation.organization_id == org_id)

    # ---- Overall ----
    overall = (
        base.with_entities(
            func.count(AgentInvocation.id).label("total"),
            func.sum(case((AgentInvocation.status == "success", 1), else_=0)).label("successes"),
            func.avg(AgentInvocation.duration_ms).label("avg_duration"),
            func.sum(AgentInvocation.tokens_used).label("total_tokens"),
            func.sum(AgentInvocation.cost_estimate).label("total_cost"),
        )
        .one()
    )

    total = overall.total or 0
    successes = overall.successes or 0
    success_rate = round((successes / total) * 100, 2) if total > 0 else 0.0

    # ---- By agent role ----
    role_rows = (
        base.with_entities(
            AgentInvocation.agent_role,
            func.count(AgentInvocation.id).label("invocations"),
            func.sum(case((AgentInvocation.status == "success", 1), else_=0)).label("successes"),
            func.avg(AgentInvocation.duration_ms).label("avg_duration"),
        )
        .group_by(AgentInvocation.agent_role)
        .order_by(desc("invocations"))
        .all()
    )

    by_role = []
    for row in role_rows:
        role_total = row.invocations or 0
        role_success = row.successes or 0
        # Find the most-used tool for this role
        top_tool_row = (
            base.filter(AgentInvocation.agent_role == row.agent_role)
            .with_entities(
                AgentInvocation.tool_name,
                func.count(AgentInvocation.id).label("cnt"),
            )
            .group_by(AgentInvocation.tool_name)
            .order_by(desc("cnt"))
            .first()
        )
        by_role.append({
            "agent_role": row.agent_role,
            "invocations": role_total,
            "success_rate": round((role_success / role_total) * 100, 2) if role_total else 0.0,
            "avg_duration_ms": round(float(row.avg_duration or 0), 1),
            "most_used_tool": top_tool_row.tool_name if top_tool_row else None,
        })

    # ---- By tool ----
    tool_rows = (
        base.with_entities(
            AgentInvocation.tool_name,
            func.count(AgentInvocation.id).label("invocations"),
            func.sum(case((AgentInvocation.status == "success", 1), else_=0)).label("successes"),
            func.avg(AgentInvocation.duration_ms).label("avg_duration"),
        )
        .group_by(AgentInvocation.tool_name)
        .order_by(desc("invocations"))
        .limit(50)
        .all()
    )

    by_tool = [
        {
            "tool_name": row.tool_name,
            "invocations": row.invocations or 0,
            "success_rate": round(((row.successes or 0) / (row.invocations or 1)) * 100, 2),
            "avg_duration_ms": round(float(row.avg_duration or 0), 1),
        }
        for row in tool_rows
    ]

    # ---- Error distribution ----
    error_rows = (
        base.filter(AgentInvocation.status != "success")
        .with_entities(
            AgentInvocation.status,
            func.count(AgentInvocation.id).label("count"),
        )
        .group_by(AgentInvocation.status)
        .order_by(desc("count"))
        .all()
    )

    error_distribution = [
        {"status": row.status, "count": row.count}
        for row in error_rows
    ]

    return {
        "period_days": days,
        "total_invocations": total,
        "success_rate": success_rate,
        "avg_duration_ms": round(float(overall.avg_duration or 0), 1),
        "total_tokens": int(overall.total_tokens or 0),
        "total_cost": round(float(overall.total_cost or 0), 6),
        "by_agent_role": by_role,
        "by_tool": by_tool,
        "error_distribution": error_distribution,
    }


# ---------------------------------------------------------------------------
# Read path — slow tools
# ---------------------------------------------------------------------------

def get_slow_tools(
    db: Session,
    threshold_ms: int = 5000,
    org_id: Optional[int] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Return tools whose average duration exceeds *threshold_ms*.

    Each entry includes the tool name, average duration, p95 estimate,
    invocation count, and representative agent role.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(AgentInvocation).filter(
        AgentInvocation.created_at >= cutoff,
        AgentInvocation.duration_ms.isnot(None),
    )
    if org_id is not None:
        base = base.filter(AgentInvocation.organization_id == org_id)

    rows = (
        base.with_entities(
            AgentInvocation.tool_name,
            func.count(AgentInvocation.id).label("invocations"),
            func.avg(AgentInvocation.duration_ms).label("avg_duration"),
            func.max(AgentInvocation.duration_ms).label("max_duration"),
            func.min(AgentInvocation.duration_ms).label("min_duration"),
        )
        .group_by(AgentInvocation.tool_name)
        .having(func.avg(AgentInvocation.duration_ms) > threshold_ms)
        .order_by(desc("avg_duration"))
        .all()
    )

    results = []
    for row in rows:
        # Find primary agent role for this tool
        role_row = (
            base.filter(AgentInvocation.tool_name == row.tool_name)
            .with_entities(
                AgentInvocation.agent_role,
                func.count(AgentInvocation.id).label("cnt"),
            )
            .group_by(AgentInvocation.agent_role)
            .order_by(desc("cnt"))
            .first()
        )

        results.append({
            "tool_name": row.tool_name,
            "invocations": row.invocations,
            "avg_duration_ms": round(float(row.avg_duration or 0), 1),
            "max_duration_ms": row.max_duration,
            "min_duration_ms": row.min_duration,
            "primary_agent_role": role_row.agent_role if role_row else None,
        })

    return results


# ---------------------------------------------------------------------------
# Read path — error patterns
# ---------------------------------------------------------------------------

def get_error_patterns(
    db: Session,
    days: int = 7,
    org_id: Optional[int] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Return the most common error patterns in the given window.

    Groups by (tool_name, status, truncated error_message) to surface
    recurring failures.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(AgentInvocation).filter(
        AgentInvocation.created_at >= cutoff,
        AgentInvocation.status != "success",
    )
    if org_id is not None:
        base = base.filter(AgentInvocation.organization_id == org_id)

    rows = (
        base.with_entities(
            AgentInvocation.tool_name,
            AgentInvocation.agent_role,
            AgentInvocation.status,
            AgentInvocation.error_message,
            func.count(AgentInvocation.id).label("occurrences"),
            func.min(AgentInvocation.created_at).label("first_seen"),
            func.max(AgentInvocation.created_at).label("last_seen"),
        )
        .group_by(
            AgentInvocation.tool_name,
            AgentInvocation.agent_role,
            AgentInvocation.status,
            AgentInvocation.error_message,
        )
        .order_by(desc("occurrences"))
        .limit(limit)
        .all()
    )

    return [
        {
            "tool_name": row.tool_name,
            "agent_role": row.agent_role,
            "status": row.status,
            "error_message": (row.error_message or "")[:500],
            "occurrences": row.occurrences,
            "first_seen": row.first_seen.isoformat() if row.first_seen else None,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in rows
    ]
