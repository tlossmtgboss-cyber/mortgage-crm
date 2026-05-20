"""
Learning Pipeline Agents

Replaces the 4 Celery-based learning tasks from tasks/learning_tasks.py that
never ran in production (no Celery worker deployed).  Re-implemented as
APScheduler-compatible autonomous agents using the @autonomous_agent decorator.

Agents:
1. confidence_recalculator  — Daily 2 AM.  Batch-evaluate all action types for graduation.
2. agent_health_monitor     — Every 6 hours.  Detect high failure rates and trigger revocation.
3. stale_approval_cleanup   — Daily 4 AM.  Expire pending_approval actions older than 7 days.
4. confidence_stats_logger  — Daily 5 AM.  Log confidence dashboard snapshot for diagnostics.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Confidence Recalculator
# ---------------------------------------------------------------------------

@autonomous_agent(
    name="confidence_recalculator",
    description="Batch-evaluate all action types for confidence graduation",
    frequency=AgentFrequency.DAILY_2AM,
    max_runtime_seconds=120,
)
def confidence_recalculator(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    For each org, call ConfidenceGraduationService.evaluate_graduations()
    to batch-check all non-graduated action types.  Cheap to run daily
    since it only recalculates scores and promotes those above threshold.
    """
    from services.autonomous.confidence_graduation import ConfidenceGraduationService

    service = ConfidenceGraduationService(db)
    graduated = service.evaluate_graduations(organization_id)

    db.commit()

    summary_parts = []
    if graduated:
        names = ", ".join(g["action_type"] for g in graduated)
        summary_parts.append(f"Graduated: {names}")
    else:
        summary_parts.append("No new graduations")

    return {
        "actions_taken": len(graduated),
        "notifications_sent": 0,
        "summary": "; ".join(summary_parts),
        "graduated": graduated,
    }


# ---------------------------------------------------------------------------
# 2. Agent Health Monitor
# ---------------------------------------------------------------------------

@autonomous_agent(
    name="agent_health_monitor",
    description="Detect high failure rates in auto-executed actions and trigger revocation",
    frequency=AgentFrequency.EVERY_6_HOURS,
    max_runtime_seconds=120,
)
def agent_health_monitor(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Query recent AgentAction records for each action_type.  If any type has
    >10% failure rate in the last 50 auto-executed actions, call
    record_auto_execution(success=False) to trigger the revocation check
    inside ConfidenceGraduationService.
    """
    from database.models.autonomous_task import AgentAction
    from services.autonomous.confidence_graduation import (
        ConfidenceGraduationService,
        REVOCATION_WINDOW,
    )

    # Find distinct action types with recent auto-executed actions for this org
    action_types_rows = db.execute(text("""
        SELECT DISTINCT action_type
        FROM agent_actions
        WHERE organization_id = :org_id
          AND requires_approval = false
          AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
    """), {"org_id": organization_id}).fetchall()

    action_types = [row[0] for row in action_types_rows]
    if not action_types:
        return {
            "actions_taken": 0,
            "notifications_sent": 0,
            "summary": "No auto-executed actions in last 7 days",
        }

    service = ConfidenceGraduationService(db)
    flagged = []

    for action_type in action_types:
        # Get last N auto-executed actions for this type
        recent = (
            db.query(AgentAction)
            .filter(
                AgentAction.organization_id == organization_id,
                AgentAction.action_type == action_type,
                AgentAction.requires_approval.is_(False),
            )
            .order_by(AgentAction.created_at.desc())
            .limit(REVOCATION_WINDOW)
            .all()
        )

        if len(recent) < 10:
            continue

        failures = sum(1 for a in recent if a.status == "failed")
        failure_rate = failures / len(recent)

        if failure_rate > 0.10:
            # Record failure to let ConfidenceGraduationService handle revocation
            service.record_auto_execution(
                org_id=organization_id,
                action_type=action_type,
                success=False,
            )
            flagged.append({
                "action_type": action_type,
                "failure_rate": round(failure_rate * 100, 1),
                "sample_size": len(recent),
                "failures": failures,
            })
            logger.warning(
                "High failure rate for '%s' org %d: %.1f%% (%d/%d)",
                action_type, organization_id, failure_rate * 100,
                failures, len(recent),
            )

    db.commit()

    if flagged:
        names = ", ".join(f["action_type"] for f in flagged)
        summary = f"Flagged {len(flagged)} action types with high failure rate: {names}"
    else:
        summary = f"All {len(action_types)} action types healthy"

    return {
        "actions_taken": len(flagged),
        "notifications_sent": 0,
        "summary": summary,
        "checked": len(action_types),
        "flagged": flagged,
    }


# ---------------------------------------------------------------------------
# 3. Stale Approval Cleanup
# ---------------------------------------------------------------------------

@autonomous_agent(
    name="stale_approval_cleanup",
    description="Expire pending_approval agent actions older than 7 days",
    frequency=AgentFrequency.DAILY_4AM,
    max_runtime_seconds=60,
)
def stale_approval_cleanup(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Find AgentAction records stuck in 'pending_approval' status for more
    than 7 days and mark them as 'expired'.  Stale approvals should not
    block the learning pipeline indefinitely.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    result = db.execute(text("""
        UPDATE agent_actions
        SET status = 'expired'
        WHERE organization_id = :org_id
          AND status = 'pending_approval'
          AND created_at < :cutoff
    """), {"org_id": organization_id, "cutoff": cutoff})

    expired_count = result.rowcount
    db.commit()

    if expired_count > 0:
        logger.info(
            "Expired %d stale pending_approval actions for org %d",
            expired_count, organization_id,
        )

    return {
        "actions_taken": expired_count,
        "notifications_sent": 0,
        "summary": f"Expired {expired_count} stale approval(s)" if expired_count else "No stale approvals",
        "expired_count": expired_count,
    }


# ---------------------------------------------------------------------------
# 4. Confidence Stats Logger
# ---------------------------------------------------------------------------

@autonomous_agent(
    name="confidence_stats_logger",
    description="Log confidence dashboard snapshot for diagnostics",
    frequency=AgentFrequency.DAILY_5AM,
    max_runtime_seconds=60,
)
def confidence_stats_logger(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """
    Query ActionTypeConfidence for each org, compute summary stats
    (graduated vs non-graduated, average confidence, total actions),
    and log to the agent_run_log table as a diagnostic run.
    The run is logged automatically by the loop infrastructure via
    _log_execution, so we just return the stats as the summary.
    """
    from database.models.action_type_confidence import ActionTypeConfidence

    records = (
        db.query(ActionTypeConfidence)
        .filter_by(organization_id=organization_id)
        .all()
    )

    if not records:
        return {
            "actions_taken": 0,
            "notifications_sent": 0,
            "summary": "No action types tracked yet",
            "stats": {},
        }

    graduated = [r for r in records if r.is_graduated]
    non_graduated = [r for r in records if not r.is_graduated]

    scores = [float(r.confidence_score) for r in records if r.confidence_score is not None]
    avg_confidence = sum(scores) / len(scores) if scores else 0.0

    total_proposed = sum(r.total_proposed or 0 for r in records)
    total_approved = sum(r.total_approved or 0 for r in records)
    total_rejected = sum(r.total_rejected or 0 for r in records)
    total_auto = sum(r.total_auto_executed or 0 for r in records)

    stats = {
        "total_action_types": len(records),
        "graduated_count": len(graduated),
        "non_graduated_count": len(non_graduated),
        "avg_confidence_score": round(avg_confidence, 4),
        "total_proposed": total_proposed,
        "total_approved": total_approved,
        "total_rejected": total_rejected,
        "total_auto_executed": total_auto,
        "graduated_types": [r.action_type for r in graduated],
        "approaching_graduation": [
            {
                "action_type": r.action_type,
                "confidence": float(r.confidence_score),
                "decisions": r.total_decisions,
            }
            for r in non_graduated
            if r.confidence_score is not None and float(r.confidence_score) >= 0.80
        ],
    }

    summary = (
        f"{len(graduated)}/{len(records)} graduated, "
        f"avg confidence {avg_confidence:.4f}, "
        f"{total_proposed} proposed, {total_auto} auto-executed"
    )

    logger.info(
        "Confidence stats for org %d: %s", organization_id, summary,
    )

    return {
        "actions_taken": 0,
        "notifications_sent": 0,
        "summary": summary,
        "stats": stats,
    }
