"""
Agent Background Tasks

Scheduled jobs for:
- Agent health checks (every 5 minutes)
- Metrics aggregation (every hour)
- Alert cleanup (daily)
- Performance snapshots (hourly)
- Stale execution cleanup (daily)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database import SessionLocal
from db import get_db_with_tenant
from models.agent_governance import (
    AgentProfile, AgentExecution, AgentAlert, AgentMetricsTimeseries,
    AgentChatSession, HealthStatus, AlertSeverity, AlertStatus
)

logger = logging.getLogger(__name__)


def get_db_session():
    """Create a new database session for background tasks.

    Note: Background tasks run outside the FastAPI request lifecycle,
    so RLS context is not available from middleware. For tenant-scoped
    background work, use get_db_with_tenant(org_id) instead.
    """
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Error creating DB session: {e}")
        db.close()
        raise


# ============================================================================
# Health Check Task
# ============================================================================

def run_agent_health_checks():
    """
    Background task to check health of all agents.
    Should run every 5 minutes.
    Updates agent health_status based on recent executions and error rates.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting agent health check task...")

        results = {
            "checked": 0,
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "alerts_created": 0
        }

        # Get all active agents
        agents = db.query(AgentProfile).filter(
            AgentProfile.status == 'active'
        ).all()

        for agent in agents:
            health_result = check_agent_health(db, agent)
            results["checked"] += 1

            if health_result["status"] == "healthy":
                results["healthy"] += 1
            elif health_result["status"] == "warning":
                results["warning"] += 1
            elif health_result["status"] == "critical":
                results["critical"] += 1

            if health_result.get("alert_created"):
                results["alerts_created"] += 1

            # Update agent health status
            agent.health_status = health_result["status"]
            agent.last_health_check = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Agent health check complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Error in agent health check task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


def check_agent_health(db: Session, agent: AgentProfile) -> Dict[str, Any]:
    """Check health for a single agent."""
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(hours=1)

    # Get recent executions
    recent_executions = db.query(AgentExecution).filter(
        AgentExecution.agent_id == agent.id,
        AgentExecution.created_at >= lookback
    ).all()

    result = {
        "agent_id": agent.id,
        "agent_name": agent.agent_name,
        "status": "healthy",
        "metrics": {},
        "alert_created": False
    }

    if not recent_executions:
        # No recent activity - check if agent was recently active
        if agent.last_execution_at:
            hours_since_activity = (now - agent.last_execution_at).total_seconds() / 3600
            if hours_since_activity > 24:
                result["status"] = "warning"
                result["reason"] = "No activity in 24+ hours"
        return result

    # Calculate metrics
    total = len(recent_executions)
    successful = len([e for e in recent_executions if e.success])
    failed = len([e for e in recent_executions if e.success == False])
    error_rate = (failed / total * 100) if total > 0 else 0

    response_times = [e.response_time_ms for e in recent_executions if e.response_time_ms]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0

    result["metrics"] = {
        "total_executions": total,
        "successful": successful,
        "failed": failed,
        "error_rate": error_rate,
        "avg_response_time_ms": avg_response_time
    }

    # Determine health status
    if error_rate >= 50:
        result["status"] = "critical"
        result["reason"] = f"High error rate: {error_rate:.1f}%"
        create_health_alert(db, agent, "critical", f"Error rate at {error_rate:.1f}%")
        result["alert_created"] = True
    elif error_rate >= 20:
        result["status"] = "warning"
        result["reason"] = f"Elevated error rate: {error_rate:.1f}%"
    elif avg_response_time > 10000:  # 10 seconds
        result["status"] = "warning"
        result["reason"] = f"High response time: {avg_response_time:.0f}ms"

    return result


def create_health_alert(
    db: Session,
    agent: AgentProfile,
    severity: str,
    message: str
):
    """Create a health-related alert for an agent."""
    # Check if similar alert exists in last hour
    existing = db.query(AgentAlert).filter(
        AgentAlert.agent_id == agent.id,
        AgentAlert.alert_type == "health",
        AgentAlert.status == "active",
        AgentAlert.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)
    ).first()

    if existing:
        return  # Don't create duplicate alerts

    alert = AgentAlert(
        agent_id=agent.id,
        agent_name=agent.agent_name,
        alert_type="health",
        severity=severity,
        title=f"Health issue: {agent.display_name or agent.agent_name}",
        message=message,
        status="active",
        details={"reason": message}
    )
    db.add(alert)


# ============================================================================
# Metrics Aggregation Task
# ============================================================================

def aggregate_agent_metrics():
    """
    Background task to aggregate metrics for all agents.
    Should run every hour.
    Creates time-series metrics records for trending.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting agent metrics aggregation task...")

        now = datetime.now(timezone.utc)
        # Round to start of hour
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        results = {"agents_processed": 0, "metrics_created": 0}

        # Get all agents
        agents = db.query(AgentProfile).all()

        for agent in agents:
            metrics = calculate_agent_metrics(db, agent, hour_start, hour_end)
            if metrics:
                # Create timeseries record
                ts_record = AgentMetricsTimeseries(
                    agent_id=agent.id,
                    agent_name=agent.agent_name,
                    timestamp=hour_start,
                    period_type="hour",
                    execution_count=metrics["execution_count"],
                    success_count=metrics["success_count"],
                    failure_count=metrics["failure_count"],
                    avg_response_time_ms=metrics["avg_response_time_ms"],
                    min_response_time_ms=metrics.get("min_response_time_ms"),
                    max_response_time_ms=metrics.get("max_response_time_ms"),
                    total_cost=metrics.get("total_cost", 0),
                    total_tokens=metrics.get("total_tokens", 0),
                    error_rate=metrics["error_rate"],
                    tool_usage=metrics.get("tool_usage", {})
                )
                db.add(ts_record)
                results["metrics_created"] += 1

                # Update agent profile metrics
                update_agent_profile_metrics(db, agent, metrics)

            results["agents_processed"] += 1

        db.commit()
        logger.info(f"Agent metrics aggregation complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Error in agent metrics aggregation task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


def calculate_agent_metrics(
    db: Session,
    agent: AgentProfile,
    start: datetime,
    end: datetime
) -> Optional[Dict[str, Any]]:
    """Calculate metrics for an agent in a time window."""
    executions = db.query(AgentExecution).filter(
        AgentExecution.agent_id == agent.id,
        AgentExecution.created_at >= start,
        AgentExecution.created_at < end
    ).all()

    if not executions:
        return None

    total = len(executions)
    successful = len([e for e in executions if e.success])
    failed = len([e for e in executions if e.success == False])

    response_times = [e.response_time_ms for e in executions if e.response_time_ms]

    # Calculate tool usage
    tool_usage = {}
    for e in executions:
        if e.tool_calls:
            for call in e.tool_calls:
                tool_name = call.get("tool_name", "unknown")
                if tool_name not in tool_usage:
                    tool_usage[tool_name] = {"count": 0, "success": 0}
                tool_usage[tool_name]["count"] += 1
                if e.success:
                    tool_usage[tool_name]["success"] += 1

    total_tokens = sum(e.tokens_used or 0 for e in executions)
    total_cost = sum(float(e.total_cost or 0) for e in executions)

    return {
        "execution_count": total,
        "success_count": successful,
        "failure_count": failed,
        "error_rate": (failed / total * 100) if total > 0 else 0,
        "avg_response_time_ms": sum(response_times) / len(response_times) if response_times else 0,
        "min_response_time_ms": min(response_times) if response_times else None,
        "max_response_time_ms": max(response_times) if response_times else None,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "tool_usage": tool_usage
    }


def update_agent_profile_metrics(
    db: Session,
    agent: AgentProfile,
    metrics: Dict[str, Any]
):
    """Update agent profile with aggregated metrics."""
    agent.total_executions = (agent.total_executions or 0) + metrics["execution_count"]
    agent.successful_executions = (agent.successful_executions or 0) + metrics["success_count"]
    agent.failed_executions = (agent.failed_executions or 0) + metrics["failure_count"]

    # Calculate overall success rate
    total = agent.total_executions or 0
    if total > 0:
        agent.success_rate = (agent.successful_executions / total) * 100

    # Update average response time (rolling average)
    if metrics["avg_response_time_ms"]:
        if agent.avg_response_time_ms:
            # Weighted average
            agent.avg_response_time_ms = (
                agent.avg_response_time_ms * 0.9 + metrics["avg_response_time_ms"] * 0.1
            )
        else:
            agent.avg_response_time_ms = metrics["avg_response_time_ms"]


# ============================================================================
# Alert Cleanup Task
# ============================================================================

def cleanup_old_alerts():
    """
    Background task to clean up old resolved alerts.
    Should run daily.
    Archives alerts older than 30 days.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting alert cleanup task...")

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        # Delete old resolved alerts
        deleted = db.query(AgentAlert).filter(
            AgentAlert.status == "resolved",
            AgentAlert.resolved_at < cutoff
        ).delete(synchronize_session=False)

        # Auto-resolve very old active alerts
        old_alerts = db.query(AgentAlert).filter(
            AgentAlert.status == "active",
            AgentAlert.created_at < cutoff
        ).all()

        for alert in old_alerts:
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolution_notes = "Auto-resolved due to age"

        db.commit()
        logger.info(f"Alert cleanup complete: {deleted} deleted, {len(old_alerts)} auto-resolved")
        return {"deleted": deleted, "auto_resolved": len(old_alerts)}

    except Exception as e:
        logger.error(f"Error in alert cleanup task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


# ============================================================================
# Stale Execution Cleanup Task
# ============================================================================

def cleanup_stale_executions():
    """
    Background task to handle stale executions.
    Should run hourly.
    Marks executions stuck in 'running' state for too long.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting stale execution cleanup task...")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

        # Find stale executions
        stale = db.query(AgentExecution).filter(
            AgentExecution.status == "running",
            AgentExecution.started_at < cutoff
        ).all()

        for execution in stale:
            execution.status = "timeout"
            execution.success = False
            execution.error_message = "Execution timed out"
            execution.completed_at = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Stale execution cleanup complete: {len(stale)} marked as timeout")
        return {"stale_executions": len(stale)}

    except Exception as e:
        logger.error(f"Error in stale execution cleanup task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


# ============================================================================
# Session Cleanup Task
# ============================================================================

def cleanup_inactive_sessions():
    """
    Background task to close inactive chat sessions.
    Should run daily.
    Closes sessions with no activity for 24 hours.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting inactive session cleanup task...")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Find and close inactive sessions
        inactive = db.query(AgentChatSession).filter(
            AgentChatSession.is_active == True,
            AgentChatSession.last_activity_at < cutoff
        ).all()

        for session in inactive:
            session.is_active = False
            session.ended_at = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Inactive session cleanup complete: {len(inactive)} sessions closed")
        return {"sessions_closed": len(inactive)}

    except Exception as e:
        logger.error(f"Error in inactive session cleanup task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


# ============================================================================
# Performance Snapshot Task
# ============================================================================

def create_daily_performance_snapshot():
    """
    Background task to create daily performance snapshot.
    Should run at end of day (midnight).
    Creates aggregate performance metrics for reporting.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting daily performance snapshot task...")

        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        # Get all agents
        agents = db.query(AgentProfile).all()

        snapshots_created = 0

        for agent in agents:
            metrics = calculate_agent_metrics(db, agent, start, end)
            if metrics and metrics["execution_count"] > 0:
                # Create daily snapshot
                snapshot = AgentMetricsTimeseries(
                    agent_id=agent.id,
                    agent_name=agent.agent_name,
                    timestamp=start,
                    period_type="day",
                    execution_count=metrics["execution_count"],
                    success_count=metrics["success_count"],
                    failure_count=metrics["failure_count"],
                    avg_response_time_ms=metrics["avg_response_time_ms"],
                    min_response_time_ms=metrics.get("min_response_time_ms"),
                    max_response_time_ms=metrics.get("max_response_time_ms"),
                    total_cost=metrics.get("total_cost", 0),
                    total_tokens=metrics.get("total_tokens", 0),
                    error_rate=metrics["error_rate"],
                    tool_usage=metrics.get("tool_usage", {})
                )
                db.add(snapshot)
                snapshots_created += 1

        db.commit()
        logger.info(f"Daily performance snapshot complete: {snapshots_created} snapshots created")
        return {"snapshots_created": snapshots_created}

    except Exception as e:
        logger.error(f"Error in daily performance snapshot task: {e}")
        if db:
            db.rollback()
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


# ============================================================================
# Task Runner (for manual execution or testing)
# ============================================================================

def run_all_agent_tasks():
    """Run all agent background tasks (for testing/manual execution)."""
    results = {
        "health_checks": run_agent_health_checks(),
        "metrics_aggregation": aggregate_agent_metrics(),
        "alert_cleanup": cleanup_old_alerts(),
        "stale_executions": cleanup_stale_executions(),
        "inactive_sessions": cleanup_inactive_sessions()
    }
    return results
