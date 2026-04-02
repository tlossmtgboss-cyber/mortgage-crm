"""
Mission Control API Routes
System Health & AI Performance Monitoring
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from pydantic import BaseModel
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)
# Lazy import for get_db to avoid circular dependency with main.py
def get_db():
    """Wrapper for get_db to avoid circular import with main.py."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/api/mission-control", tags=["Mission Control"], dependencies=[Depends(require_auth)])


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
            "last_updated": datetime.now(timezone.utc)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get system health")


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
        raise HTTPException(status_code=500, detail="Failed to get AI metrics")


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
        raise HTTPException(status_code=500, detail="Failed to get integrations")


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
        raise HTTPException(status_code=500, detail="Failed to get jobs")


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
        raise HTTPException(status_code=500, detail="Failed to get alerts")


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
        raise HTTPException(status_code=500, detail="Failed to resolve alert")


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
        raise HTTPException(status_code=500, detail="Failed to get security snapshot")


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
        raise HTTPException(status_code=500, detail="Failed to get changelog")


@router.post("/refresh")
async def refresh_system_check(db: Session = Depends(get_db)):
    """Manually trigger system health check and update integration statuses"""
    import httpx
    import os
    from datetime import datetime

    results = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "integrations": {},
        "jobs_checked": 0,
        "total_checks": 0
    }

    try:
        # Define integrations to check
        integrations_config = [
            {
                "name": "anthropic_api",
                "type": "api",
                "url": "https://api.anthropic.com/v1/messages",
                "headers": {"x-api-key": os.getenv("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"},
                "method": "health_check"
            },
            {
                "name": "openai_api",
                "type": "api",
                "url": "https://api.openai.com/v1/models",
                "headers": {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"},
                "method": "get"
            },
            {
                "name": "telnyx_sms",
                "type": "api",
                "url": "https://api.telnyx.com/v2/messaging_profiles",
                "auth": None,
                "method": "get"
            },
            {
                "name": "sendgrid_email",
                "type": "api",
                "url": "https://api.sendgrid.com/v3/user/account",
                "headers": {"Authorization": f"Bearer {os.getenv('SENDGRID_API_KEY', '')}"},
                "method": "get"
            },
            {
                "name": "aws_s3",
                "type": "s3",
                "bucket": os.getenv("AWS_S3_BUCKET", ""),
                "region": os.getenv("AWS_REGION", "us-east-1")
            },
            {
                "name": "database",
                "type": "database",
                "query": "SELECT 1"
            },
            {
                "name": "redis_cache",
                "type": "redis",
                "url": os.getenv("REDIS_URL", "")
            }
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for integration in integrations_config:
                name = integration["name"]
                results["total_checks"] += 1
                start_time = datetime.now(timezone.utc)

                try:
                    status = "healthy"
                    latency_ms = None
                    error_msg = None

                    if integration["type"] == "api":
                        # Skip if no API key configured
                        headers = integration.get("headers", {})
                        auth = integration.get("auth")

                        # Check if credentials are configured
                        has_creds = True
                        if headers:
                            for v in headers.values():
                                if not v or v.endswith("Bearer "):
                                    has_creds = False
                                    break
                        if auth and (not auth[0] or not auth[1]):
                            has_creds = False

                        if not has_creds:
                            status = "not_configured"
                            error_msg = "API credentials not configured"
                        else:
                            try:
                                if auth:
                                    response = await client.get(integration["url"], auth=auth)
                                else:
                                    response = await client.get(integration["url"], headers=headers)

                                latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                                if response.status_code < 400:
                                    status = "healthy"
                                elif response.status_code == 401:
                                    status = "auth_error"
                                    error_msg = "Authentication failed"
                                elif response.status_code == 429:
                                    status = "rate_limited"
                                    error_msg = "Rate limited"
                                else:
                                    status = "degraded"
                                    error_msg = f"HTTP {response.status_code}"
                            except httpx.TimeoutException:
                                status = "timeout"
                                error_msg = "Request timed out"
                            except httpx.ConnectError:
                                status = "down"
                                error_msg = "Connection failed"

                    elif integration["type"] == "database":
                        try:
                            db.execute(text(integration["query"]))
                            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                            status = "healthy"
                        except Exception as e:
                            status = "down"
                            error_msg = str(e)[:200]

                    elif integration["type"] == "s3":
                        bucket = integration.get("bucket")
                        if not bucket:
                            status = "not_configured"
                            error_msg = "S3 bucket not configured"
                        else:
                            try:
                                import boto3
                                s3 = boto3.client('s3', region_name=integration.get("region", "us-east-1"))
                                s3.head_bucket(Bucket=bucket)
                                latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                                status = "healthy"
                            except Exception as e:
                                status = "degraded" if "NoSuchBucket" not in str(e) else "not_configured"
                                error_msg = str(e)[:200]

                    elif integration["type"] == "redis":
                        redis_url = integration.get("url")
                        if not redis_url:
                            status = "not_configured"
                            error_msg = "Redis URL not configured"
                        else:
                            try:
                                import redis
                                r = redis.from_url(redis_url, socket_timeout=5)
                                r.ping()
                                latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                                status = "healthy"
                            except Exception as e:
                                status = "down"
                                error_msg = str(e)[:200]

                    results["integrations"][name] = {
                        "status": status,
                        "latency_ms": latency_ms,
                        "error": error_msg,
                        "checked_at": datetime.now(timezone.utc).isoformat()
                    }

                    # Update database with integration status
                    try:
                        upsert_query = text("""
                            INSERT INTO integration_status_log
                            (integration_name, status, latency_ms, last_error_message, checked_at, last_success_at, error_count_24h)
                            VALUES (:name, :status, :latency, :error, NOW(),
                                    CASE WHEN :status = 'healthy' THEN NOW() ELSE NULL END,
                                    CASE WHEN :status != 'healthy' THEN 1 ELSE 0 END)
                            ON CONFLICT (integration_name) DO UPDATE SET
                                status = :status,
                                latency_ms = :latency,
                                last_error_message = :error,
                                checked_at = NOW(),
                                last_success_at = CASE WHEN :status = 'healthy' THEN NOW() ELSE integration_status_log.last_success_at END,
                                error_count_24h = CASE WHEN :status != 'healthy'
                                    THEN COALESCE(integration_status_log.error_count_24h, 0) + 1
                                    ELSE 0 END
                        """)
                        db.execute(upsert_query, {"name": name, "status": status, "latency": latency_ms, "error": error_msg})
                    except Exception as e:
                        # Table may not exist or have different schema - just log result
                        logger.error(f"Error upserting integration status: {e}")

                except Exception as e:
                    results["integrations"][name] = {
                        "status": "error",
                        "error": "Internal server error"[:200],
                        "checked_at": datetime.now(timezone.utc).isoformat()
                    }

        db.commit()

        # Count statuses
        healthy = len([i for i in results["integrations"].values() if i["status"] == "healthy"])
        degraded = len([i for i in results["integrations"].values() if i["status"] in ["degraded", "rate_limited"]])
        down = len([i for i in results["integrations"].values() if i["status"] in ["down", "error", "timeout"]])

        results["summary"] = {
            "healthy": healthy,
            "degraded": degraded,
            "down": down,
            "not_configured": len([i for i in results["integrations"].values() if i["status"] in ["not_configured", "auth_error"]])
        }
        results["status"] = "completed"
        results["message"] = f"System check completed: {healthy} healthy, {degraded} degraded, {down} down"

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to trigger system check")
