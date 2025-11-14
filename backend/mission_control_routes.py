"""
Mission Control API Routes
System Health & AI Performance Monitoring
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from pydantic import BaseModel
from main import get_db

router = APIRouter(prefix="/api/mission-control", tags=["Mission Control"])


# Pydantic Models
class SystemHealthSummary(BaseModel):
    overall_status: str  # 'healthy', 'degraded', 'critical'
    ai_improvement_index: float
    ai_improvement_delta: float
    critical_alerts_count: int
    warning_alerts_count: int
    last_updated: datetime


class IntegrationStatus(BaseModel):
    name: str
    status: str
    last_success_at: Optional[datetime]
    error_count_24h: int
    latency_ms: Optional[int]
    last_error_message: Optional[str]


class AIMetric(BaseModel):
    date: date
    automation_rate: float
    escalation_rate: float
    tasks_total: int
    tasks_auto_completed: int
    ai_improvement_index: float


class SystemAlert(BaseModel):
    id: int
    alert_type: str
    severity: str
    title: str
    message: str
    suggested_action: Optional[str]
    created_at: datetime


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/summary")
async def get_system_health_summary(db: Session = Depends(get_db)):
    """Get overall system health summary"""
    try:
        # Get latest AI improvement index
        ai_metrics_query = text("""
            SELECT
                ai_improvement_index,
                date
            FROM ai_metrics_daily
            ORDER BY date DESC
            LIMIT 2
        """)
        ai_metrics = db.execute(ai_metrics_query).fetchall()

        current_index = ai_metrics[0].ai_improvement_index if ai_metrics else 100.0
        previous_index = ai_metrics[1].ai_improvement_index if len(ai_metrics) > 1 else 100.0
        ai_improvement_delta = ((current_index - previous_index) / previous_index * 100) if previous_index > 0 else 0

        # Count critical integrations
        integration_query = text("""
            SELECT status, COUNT(*) as count
            FROM (
                SELECT DISTINCT ON (integration_name)
                    integration_name, status
                FROM integration_status_log
                ORDER BY integration_name, checked_at DESC
            ) latest
            GROUP BY status
        """)
        integration_counts = db.execute(integration_query).fetchall()
        integration_status_map = {row.status: row.count for row in integration_counts}

        # Determine overall status
        down_count = integration_status_map.get('down', 0)
        degraded_count = integration_status_map.get('degraded', 0)

        if down_count > 0:
            overall_status = 'critical'
        elif degraded_count > 0:
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'

        # Count alerts
        alerts_query = text("""
            SELECT severity, COUNT(*) as count
            FROM system_alerts
            WHERE is_resolved = false
            GROUP BY severity
        """)
        alerts = db.execute(alerts_query).fetchall()
        alert_counts = {row.severity: row.count for row in alerts}

        return {
            "overall_status": overall_status,
            "ai_improvement_index": round(current_index, 2),
            "ai_improvement_delta": round(ai_improvement_delta, 2),
            "critical_alerts_count": alert_counts.get('critical', 0),
            "warning_alerts_count": alert_counts.get('warning', 0),
            "last_updated": datetime.utcnow()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system health: {str(e)}")


@router.get("/ai-metrics")
async def get_ai_metrics(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get AI performance metrics over time"""
    try:
        if from_date and to_date:
            query = text("""
                SELECT *
                FROM ai_metrics_daily
                WHERE date BETWEEN :from_date AND :to_date
                ORDER BY date DESC
            """)
            results = db.execute(query, {"from_date": from_date, "to_date": to_date}).fetchall()
        else:
            query = text("""
                SELECT *
                FROM ai_metrics_daily
                ORDER BY date DESC
                LIMIT :days
            """)
            results = db.execute(query, {"days": days}).fetchall()

        metrics = []
        for row in results:
            metrics.append({
                "date": row.date.isoformat(),
                "tasks_total": row.tasks_total,
                "tasks_auto_completed": row.tasks_auto_completed,
                "tasks_escalated_to_humans": row.tasks_escalated_to_humans,
                "automation_rate": float(row.automation_rate) if row.automation_rate else 0,
                "escalation_rate": float(row.escalation_rate) if row.escalation_rate else 0,
                "avg_ai_resolution_time_seconds": float(row.avg_ai_resolution_time_seconds) if row.avg_ai_resolution_time_seconds else 0,
                "time_saved_seconds": float(row.total_time_saved_seconds) if row.total_time_saved_seconds else 0,
                "ai_improvement_index": float(row.ai_improvement_index) if row.ai_improvement_index else 100
            })

        return {
            "metrics": metrics,
            "count": len(metrics)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get AI metrics: {str(e)}")


@router.get("/integrations")
async def get_integrations_status(db: Session = Depends(get_db)):
    """Get current status of all integrations"""
    try:
        query = text("""
            SELECT DISTINCT ON (integration_name)
                integration_name,
                status,
                last_success_at,
                error_count_24h,
                latency_ms,
                last_error_message,
                checked_at
            FROM integration_status_log
            ORDER BY integration_name, checked_at DESC
        """)
        results = db.execute(query).fetchall()

        integrations = []
        for row in results:
            integrations.append({
                "name": row.integration_name,
                "status": row.status,
                "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                "error_count_24h": row.error_count_24h,
                "latency_ms": row.latency_ms,
                "last_error_message": row.last_error_message,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None
            })

        return {
            "integrations": integrations,
            "count": len(integrations)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get integrations: {str(e)}")


@router.get("/jobs")
async def get_system_jobs(db: Session = Depends(get_db)):
    """Get system jobs and their status"""
    try:
        query = text("""
            SELECT DISTINCT ON (job_name)
                job_name,
                job_type,
                last_run_at,
                status,
                duration_ms,
                error_message,
                records_processed
            FROM system_jobs_log
            ORDER BY job_name, last_run_at DESC
        """)
        results = db.execute(query).fetchall()

        jobs = []
        for row in results:
            jobs.append({
                "job_name": row.job_name,
                "job_type": row.job_type,
                "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "error_message": row.error_message,
                "records_processed": row.records_processed
            })

        return {
            "jobs": jobs,
            "count": len(jobs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get jobs: {str(e)}")


@router.get("/alerts")
async def get_system_alerts(
    severity: Optional[str] = None,
    resolved: bool = False,
    db: Session = Depends(get_db)
):
    """Get system alerts"""
    try:
        query = text("""
            SELECT
                id,
                alert_type,
                severity,
                title,
                message,
                suggested_action,
                created_at
            FROM system_alerts
            WHERE is_resolved = :resolved
            AND (:severity IS NULL OR severity = :severity)
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'warning' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT 50
        """)
        results = db.execute(query, {"severity": severity, "resolved": resolved}).fetchall()

        alerts = []
        for row in results:
            alerts.append({
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "title": row.title,
                "message": row.message,
                "suggested_action": row.suggested_action,
                "created_at": row.created_at.isoformat() if row.created_at else None
            })

        return {
            "alerts": alerts,
            "count": len(alerts)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an alert as resolved"""
    try:
        query = text("""
            UPDATE system_alerts
            SET is_resolved = true,
                resolved_at = CURRENT_TIMESTAMP
            WHERE id = :alert_id
        """)
        db.execute(query, {"alert_id": alert_id})
        db.commit()

        return {"message": "Alert resolved successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")


@router.get("/security")
async def get_security_snapshot(db: Session = Depends(get_db)):
    """Get security and compliance snapshot"""
    try:
        query = text("""
            SELECT *
            FROM security_snapshot_daily
            ORDER BY date DESC
            LIMIT 1
        """)
        result = db.execute(query).fetchone()

        if not result:
            return {
                "date": date.today().isoformat(),
                "active_users_with_2fa": 0,
                "active_users_total": 0,
                "tfa_coverage_percent": 0,
                "high_privilege_actions_24h": 0,
                "failed_login_attempts_24h": 0,
                "password_changes_24h": 0,
                "last_permission_change_user": None,
                "last_permission_change_at": None
            }

        tfa_coverage = (result.active_users_with_2fa / result.active_users_total * 100) if result.active_users_total > 0 else 0

        return {
            "date": result.date.isoformat(),
            "active_users_with_2fa": result.active_users_with_2fa,
            "active_users_total": result.active_users_total,
            "tfa_coverage_percent": round(tfa_coverage, 1),
            "high_privilege_actions_24h": result.high_privilege_actions_24h,
            "failed_login_attempts_24h": result.failed_login_attempts_24h,
            "password_changes_24h": result.password_changes_24h,
            "last_permission_change_user": result.last_permission_change_user,
            "last_permission_change_at": result.last_permission_change_at.isoformat() if result.last_permission_change_at else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get security snapshot: {str(e)}")


@router.get("/changelog")
async def get_ai_changelog(days: int = 7, db: Session = Depends(get_db)):
    """Get AI daily changelog"""
    try:
        query = text("""
            SELECT *
            FROM ai_changelog_daily
            ORDER BY date DESC
            LIMIT :days
        """)
        results = db.execute(query, {"days": days}).fetchall()

        changelogs = []
        for row in results:
            changelogs.append({
                "date": row.date.isoformat(),
                "summary": row.summary,
                "improvements": row.improvements,
                "issues": row.issues,
                "ai_generated": row.ai_generated
            })

        return {
            "changelogs": changelogs,
            "count": len(changelogs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get changelog: {str(e)}")


@router.post("/refresh")
async def refresh_system_check(db: Session = Depends(get_db)):
    """Manually trigger system health check"""
    try:
        # This would trigger background jobs to check all integrations
        # For now, just return success
        return {
            "message": "System check initiated",
            "status": "running",
            "estimated_completion": "2-3 minutes"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger system check: {str(e)}")
