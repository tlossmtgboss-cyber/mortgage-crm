"""
Mission Control API Routes
AI Colleague Performance & Autonomous Operations Dashboard
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timedelta, timezone
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)
from db import get_db

router = APIRouter(
    prefix="/api/v1/mission-control",
    tags=["Mission Control"],
    dependencies=[Depends(require_auth)]
)


# ============================================================================
# PRIMARY ENDPOINTS (consumed by frontend MissionControl.js)
# ============================================================================

@router.get("/health")
async def get_ai_health(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """AI health score with component breakdown — primary dashboard endpoint."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # TODO: Add organization_id filter for tenant isolation. The ai_colleague_actions
        # table has an organization_id column, but these endpoints use require_auth (not
        # get_current_user), so org_id is not available here. Wiring up get_current_user
        # requires changes to the router dependency and all endpoints in this file.
        totals = db.execute(text("""
            SELECT
                COUNT(*) as total_actions,
                COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous_actions,
                COUNT(*) FILTER (WHERE outcome = 'success') as successful_actions,
                COUNT(*) FILTER (WHERE required_approval = true AND status = 'completed') as approved_actions,
                COUNT(*) FILTER (WHERE required_approval = true) as approval_required,
                AVG(confidence_score) FILTER (WHERE confidence_score IS NOT NULL) as avg_confidence
            FROM ai_colleague_actions
            WHERE created_at >= :cutoff
        """), {"cutoff": cutoff}).fetchone()

        total = totals.total_actions or 0
        autonomous = totals.autonomous_actions or 0
        successful = totals.successful_actions or 0
        approved = totals.approved_actions or 0
        approval_required = totals.approval_required or 0
        avg_confidence = float(totals.avg_confidence or 0)

        autonomy_score = (autonomous / total * 100) if total > 0 else 0
        accuracy_score = (successful / total * 100) if total > 0 else 0
        approval_score = (approved / approval_required * 100) if approval_required > 0 else 0
        confidence_score = avg_confidence

        overall_score = (
            autonomy_score * 0.25 +
            accuracy_score * 0.35 +
            approval_score * 0.20 +
            confidence_score * 0.20
        )

        if overall_score >= 80:
            health_status = "excellent"
        elif overall_score >= 60:
            health_status = "good"
        elif overall_score >= 40:
            health_status = "fair"
        else:
            health_status = "needs_attention"

        return {
            "overall_score": round(overall_score, 1),
            "health_status": health_status,
            "metrics": {
                "total_actions": total,
                "autonomous_actions": autonomous,
            },
            "component_scores": {
                "autonomy": round(autonomy_score, 1),
                "accuracy": round(accuracy_score, 1),
                "approval": round(approval_score, 1),
                "confidence": round(confidence_score, 1),
            }
        }

    except Exception as e:
        logger.warning(f"Mission control health query failed (table may not exist): {e}")
        return {
            "overall_score": 0,
            "health_status": "needs_attention",
            "metrics": {"total_actions": 0, "autonomous_actions": 0},
            "component_scores": {"autonomy": 0, "accuracy": 0, "approval": 0, "confidence": 0}
        }


@router.get("/metrics")
async def get_agent_metrics(
    days: int = Query(default=7, ge=1, le=90),
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Per-agent performance metrics breakdown."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        params = {"cutoff": cutoff}

        agent_filter = ""
        if agent_name:
            agent_filter = "AND agent_name = :agent_name"
            params["agent_name"] = agent_name

        rows = db.execute(text(f"""
            SELECT
                agent_name,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
                COUNT(*) FILTER (WHERE outcome = 'success') as successful,
                AVG(confidence_score) FILTER (WHERE confidence_score IS NOT NULL) as avg_confidence
            FROM ai_colleague_actions
            WHERE created_at >= :cutoff {agent_filter}
            GROUP BY agent_name
            ORDER BY total DESC
        """), params).fetchall()

        agents = {}
        for row in rows:
            total = row.total or 0
            agents[row.agent_name] = {
                "total": total,
                "autonomous": row.autonomous or 0,
                "autonomy_rate": round((row.autonomous or 0) / total * 100, 0) if total > 0 else 0,
                "success_rate": round((row.successful or 0) / total * 100, 0) if total > 0 else 0,
                "avg_confidence": round(float(row.avg_confidence or 0), 0),
            }

        return {"agents": agents}

    except Exception as e:
        logger.warning(f"Mission control metrics query failed: {e}")
        return {"agents": {}}


@router.get("/recent-actions")
async def get_recent_actions(
    limit: int = Query(default=20, ge=1, le=100),
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Recent AI colleague actions for the activity feed."""
    try:
        params = {"limit": limit}
        agent_filter = ""
        if agent_name:
            agent_filter = "WHERE agent_name = :agent_name"
            params["agent_name"] = agent_name

        rows = db.execute(text(f"""
            SELECT
                id, agent_name, action_type, autonomy_level,
                outcome, confidence_score, reasoning, created_at
            FROM ai_colleague_actions
            {agent_filter}
            ORDER BY created_at DESC
            LIMIT :limit
        """), params).fetchall()

        actions = []
        for row in rows:
            actions.append({
                "id": row.id,
                "agent_name": row.agent_name,
                "action_type": row.action_type,
                "autonomy_level": row.autonomy_level,
                "outcome": row.outcome,
                "confidence_score": round(float(row.confidence_score), 0) if row.confidence_score else None,
                "reasoning": row.reasoning,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

        return {"actions": actions}

    except Exception as e:
        logger.warning(f"Mission control recent-actions query failed: {e}")
        return {"actions": []}


@router.get("/insights")
async def get_ai_insights(
    limit: int = Query(default=10, ge=1, le=50),
    status: Optional[str] = "active",
    db: Session = Depends(get_db)
):
    """AI-discovered insights and pattern recommendations.

    Queries ai_journey_insights (model: AIJourneyInsight in database/models/ai.py).
    """
    try:
        rows = db.execute(text("""
            SELECT id, insight_type, pattern_confidence, pattern_description,
                   recommended_action, priority, status, discovered_at
            FROM ai_journey_insights
            WHERE (:status IS NULL OR status = :status)
            ORDER BY discovered_at DESC
            LIMIT :limit
        """), {"status": status, "limit": limit}).fetchall()

        if not rows:
            logger.info("Mission control /insights: ai_journey_insights table not populated yet")

        insights = []
        for row in rows:
            insights.append({
                "id": row.id,
                "insight_type": row.insight_type,
                "pattern_confidence": row.pattern_confidence,
                "pattern_description": row.pattern_description,
                "recommended_action": row.recommended_action,
                "priority": row.priority,
                "discovered_at": row.discovered_at.isoformat() if row.discovered_at else None,
            })

        return {"insights": insights}

    except Exception as e:
        logger.warning(f"Mission control insights query failed: {e}")
        return {"insights": []}


# ============================================================================
# SYSTEM HEALTH ENDPOINTS (infrastructure monitoring)
# ============================================================================

@router.get("/summary")
async def get_system_health_summary(db: Session = Depends(get_db)):
    """Get overall system health summary."""
    try:
        ai_metrics = db.execute(text("""
            SELECT ai_improvement_index, date
            FROM ai_metrics_daily
            ORDER BY date DESC LIMIT 2
        """)).fetchall()

        current_index = ai_metrics[0].ai_improvement_index if ai_metrics else 100.0
        previous_index = ai_metrics[1].ai_improvement_index if len(ai_metrics) > 1 else 100.0
        delta = ((current_index - previous_index) / previous_index * 100) if previous_index > 0 else 0

        return {
            "overall_status": "healthy",
            "ai_improvement_index": round(current_index, 2),
            "ai_improvement_delta": round(delta, 2),
            "critical_alerts_count": 0,
            "warning_alerts_count": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.warning(f"System health summary query failed: {e}")
        return {
            "overall_status": "healthy",
            "ai_improvement_index": 100.0,
            "ai_improvement_delta": 0,
            "critical_alerts_count": 0,
            "warning_alerts_count": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


@router.get("/ai-metrics")
async def get_ai_metrics_daily(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get AI performance metrics over time."""
    try:
        results = db.execute(text("""
            SELECT * FROM ai_metrics_daily ORDER BY date DESC LIMIT :days
        """), {"days": days}).fetchall()

        metrics = []
        for row in results:
            metrics.append({
                "date": row.date.isoformat(),
                "tasks_total": row.tasks_total,
                "tasks_auto_completed": row.tasks_auto_completed,
                "automation_rate": float(row.automation_rate) if row.automation_rate else 0,
                "ai_improvement_index": float(row.ai_improvement_index) if row.ai_improvement_index else 100
            })
        return {"metrics": metrics, "count": len(metrics)}
    except Exception as e:
        logger.warning(f"AI metrics daily query failed: {e}")
        return {"metrics": [], "count": 0}


@router.get("/integrations")
async def get_integrations_status(db: Session = Depends(get_db)):
    """Get current status of all integrations."""
    try:
        results = db.execute(text("""
            SELECT DISTINCT ON (integration_name)
                integration_name, status, last_success_at, error_count_24h,
                latency_ms, last_error_message, checked_at
            FROM integration_status_log
            ORDER BY integration_name, checked_at DESC
        """)).fetchall()

        integrations = []
        for row in results:
            integrations.append({
                "name": row.integration_name,
                "status": row.status,
                "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                "error_count_24h": row.error_count_24h,
                "latency_ms": row.latency_ms,
                "last_error_message": row.last_error_message,
            })
        return {"integrations": integrations, "count": len(integrations)}
    except Exception as e:
        logger.warning(f"Integrations status query failed: {e}")
        return {"integrations": [], "count": 0}


@router.get("/jobs")
async def get_system_jobs(db: Session = Depends(get_db)):
    """Get system jobs and their status."""
    try:
        results = db.execute(text("""
            SELECT DISTINCT ON (job_name)
                job_name, job_type, last_run_at, status,
                duration_ms, error_message, records_processed
            FROM system_jobs_log
            ORDER BY job_name, last_run_at DESC
        """)).fetchall()

        jobs = []
        for row in results:
            jobs.append({
                "job_name": row.job_name,
                "job_type": row.job_type,
                "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "records_processed": row.records_processed,
            })
        return {"jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.warning(f"System jobs query failed: {e}")
        return {"jobs": [], "count": 0}


@router.get("/alerts")
async def get_system_alerts(
    severity: Optional[str] = None,
    resolved: bool = False,
    db: Session = Depends(get_db)
):
    """Get system alerts."""
    try:
        results = db.execute(text("""
            SELECT id, alert_type, severity, title, message, suggested_action, created_at
            FROM system_alerts
            WHERE is_resolved = :resolved
            AND (:severity IS NULL OR severity = :severity)
            ORDER BY
                CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
                created_at DESC
            LIMIT 50
        """), {"severity": severity, "resolved": resolved}).fetchall()

        alerts = []
        for row in results:
            alerts.append({
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "title": row.title,
                "message": row.message,
                "suggested_action": row.suggested_action,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.warning(f"System alerts query failed: {e}")
        return {"alerts": [], "count": 0}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an alert as resolved."""
    try:
        db.execute(text("""
            UPDATE system_alerts SET is_resolved = true, resolved_at = CURRENT_TIMESTAMP
            WHERE id = :alert_id
        """), {"alert_id": alert_id})
        db.commit()
        return {"message": "Alert resolved successfully"}
    except Exception as e:
        db.rollback()
        logger.warning(f"Resolve alert failed: {e}")
        raise HTTPException(status_code=500, detail="Could not resolve alert")


@router.get("/security")
async def get_security_snapshot(db: Session = Depends(get_db)):
    """Get security and compliance snapshot."""
    try:
        result = db.execute(text("""
            SELECT * FROM security_snapshot_daily ORDER BY date DESC LIMIT 1
        """)).fetchone()

        if not result:
            from datetime import date as date_cls
            return {
                "date": date_cls.today().isoformat(),
                "active_users_with_2fa": 0, "active_users_total": 0,
                "tfa_coverage_percent": 0, "high_privilege_actions_24h": 0,
                "failed_login_attempts_24h": 0,
            }

        tfa_coverage = (result.active_users_with_2fa / result.active_users_total * 100) if result.active_users_total > 0 else 0
        return {
            "date": result.date.isoformat(),
            "active_users_with_2fa": result.active_users_with_2fa,
            "active_users_total": result.active_users_total,
            "tfa_coverage_percent": round(tfa_coverage, 1),
            "high_privilege_actions_24h": result.high_privilege_actions_24h,
            "failed_login_attempts_24h": result.failed_login_attempts_24h,
        }
    except Exception as e:
        logger.warning(f"Security snapshot query failed: {e}")
        from datetime import date
        return {
            "date": date.today().isoformat(),
            "active_users_with_2fa": 0,
            "active_users_total": 0,
            "tfa_coverage_percent": 0,
            "high_privilege_actions_24h": 0,
            "failed_login_attempts_24h": 0,
        }


@router.get("/changelog")
async def get_ai_changelog(days: int = 7, db: Session = Depends(get_db)):
    """Get AI daily changelog."""
    try:
        results = db.execute(text("""
            SELECT * FROM ai_changelog_daily ORDER BY date DESC LIMIT :days
        """), {"days": days}).fetchall()

        changelogs = []
        for row in results:
            changelogs.append({
                "date": row.date.isoformat(),
                "summary": row.summary,
                "improvements": row.improvements,
                "issues": row.issues,
            })
        return {"changelogs": changelogs, "count": len(changelogs)}
    except Exception as e:
        logger.warning(f"AI changelog query failed: {e}")
        return {"changelogs": [], "count": 0}


@router.post("/refresh")
async def refresh_system_check(db: Session = Depends(get_db)):
    """Manually trigger system health check."""
    import httpx
    import os

    results = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "integrations": {},
        "total_checks": 0,
    }

    try:
        integrations_config = [
            {
                "name": "database",
                "type": "database",
                "query": "SELECT 1"
            },
        ]

        for integration in integrations_config:
            name = integration["name"]
            results["total_checks"] += 1
            start_time = datetime.now(timezone.utc)

            try:
                if integration["type"] == "database":
                    db.execute(text(integration["query"]))
                    latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                    results["integrations"][name] = {
                        "status": "healthy",
                        "latency_ms": latency_ms,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception as e:
                results["integrations"][name] = {
                    "status": "error",
                    "error": str(e)[:200],
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }

        healthy = len([i for i in results["integrations"].values() if i.get("status") == "healthy"])
        results["summary"] = {"healthy": healthy, "degraded": 0, "down": 0}
        results["status"] = "completed"
        results["message"] = f"System check completed: {healthy} healthy"
        return results

    except Exception as e:
        logger.warning(f"System check failed: {e}")
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "message": "System check could not complete",
            "integrations": {},
        }
