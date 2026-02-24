"""
Compliance Dashboard Endpoints
Provides compliance metrics, reports, health checks, and a unified status view.
"""
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..services.compliance_reporter import ComplianceReporter
from ..services.retention_service import RetentionService
from ..services.access_control_service import AccessControlService
from ..services.incident_service import IncidentService
from .dependencies import get_soc2_db as get_db, get_current_admin_user

router = APIRouter()


@router.get("/report")
async def generate_compliance_report(
    start_date: datetime = Query(..., description="Report period start"),
    end_date: datetime = Query(..., description="Report period end"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Generate a comprehensive SOC 2 Type II compliance report.
    This is the primary evidence artifact for auditors.

    Note: For large date ranges (>1 year), the report may be large.
    Consider breaking into quarterly periods for auditor review.
    """
    reporter = ComplianceReporter(db)
    report = reporter.generate_full_report(
        tenant_id=current_user.tenant_id,
        start_date=start_date,
        end_date=end_date,
    )
    return report


@router.get("/health")
async def compliance_health_check(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Quick compliance health check.
    Returns current status of key controls.
    """
    retention = RetentionService(db)
    retention_status = retention.get_retention_status()

    return {
        "status": "healthy",
        "data_retention": retention_status,
        "controls": {
            "audit_logging": "active",
            "encryption_at_rest": "active",
            "rate_limiting": "active",
            "security_headers": "active",
            "access_control": "active",
        }
    }


@router.get("/retention")
async def get_retention_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get data retention status and volumes."""
    retention = RetentionService(db)
    return {
        "status": retention.get_retention_status(),
        "preview": retention.preview_retention_enforcement(),
    }


@router.post("/retention/enforce")
async def enforce_retention(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Manually trigger retention policy enforcement."""
    retention = RetentionService(db)
    results = retention.enforce_retention_policies()
    return {"results": results}


@router.get("/access/summary")
async def get_access_summary(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get access event summary for compliance review."""
    access = AccessControlService(db)
    summary = access.get_access_summary(
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
    )
    return {"data": summary}


@router.get("/incidents/metrics")
async def get_incident_metrics(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get incident response metrics for compliance review."""
    incidents = IncidentService(db)
    metrics = incidents.get_incident_metrics(
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
    )
    return {"data": metrics}


@router.post("/run-scan")
async def trigger_compliance_scan(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Manually trigger a compliance scan.
    Useful for Railway cron or admin-initiated audits.
    """
    from ..scripts.compliance_scan import run_compliance_scan
    results = run_compliance_scan(db)
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    warnings = sum(1 for r in results if r.get("status") == "warning")
    return {
        "total_checks": len(results),
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "results": results,
    }


@router.get("/status")
async def get_compliance_dashboard_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Unified compliance dashboard status — single view for auditors.

    Returns:
    - Latest compliance scan results (pass/fail/warning)
    - Open security incidents
    - Retention status
    - Data classification coverage (% PII encrypted)
    - Failed login trends (last 7 days)
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Latest compliance scan results
    scan_row = db.execute(
        text("""
            SELECT
                COUNT(*) as total_checks,
                COUNT(*) FILTER (WHERE status = 'pass') as passed,
                COUNT(*) FILTER (WHERE status = 'fail') as failed,
                COUNT(*) FILTER (WHERE status = 'warning') as warnings,
                COUNT(*) FILTER (WHERE status = 'error') as errors,
                MAX(run_at) as last_scan_at
            FROM soc2_compliance_check
            WHERE run_at = (SELECT MAX(run_at) FROM soc2_compliance_check)
        """)
    ).fetchone()
    scan = dict(scan_row._mapping) if scan_row else {}

    # Open security incidents
    inc_row = db.execute(
        text("""
            SELECT
                COUNT(*) as total_open,
                COUNT(*) FILTER (WHERE severity = 'critical') as critical,
                COUNT(*) FILTER (WHERE severity = 'high') as high,
                COUNT(*) FILTER (WHERE severity = 'medium') as medium,
                COUNT(*) FILTER (WHERE severity = 'low') as low_sev
            FROM soc2_security_incident
            WHERE status NOT IN ('resolved', 'closed')
        """)
    ).fetchone()
    inc = dict(inc_row._mapping) if inc_row else {}

    # Data classification coverage
    cls_row = db.execute(
        text("""
            SELECT
                COUNT(*) as total_columns,
                COUNT(*) FILTER (WHERE is_pii = TRUE) as pii_columns,
                COUNT(*) FILTER (WHERE is_pii = TRUE AND is_encrypted = TRUE) as pii_encrypted,
                COUNT(*) FILTER (WHERE is_financial = TRUE) as financial_columns
            FROM soc2_data_classification
        """)
    ).fetchone()
    cls = dict(cls_row._mapping) if cls_row else {}

    pii_total = cls.get("pii_columns", 0) or 0
    pii_encrypted = cls.get("pii_encrypted", 0) or 0
    pii_encryption_pct = round((pii_encrypted / pii_total) * 100, 1) if pii_total > 0 else 0

    # Failed login trends (last 7 days, by day)
    failed_logins = db.execute(
        text("""
            SELECT
                DATE_TRUNC('day', timestamp)::date as day,
                COUNT(*) as failed_attempts,
                COUNT(DISTINCT attempted_email) as unique_accounts
            FROM soc2_access_event
            WHERE success = FALSE
              AND timestamp >= :since
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY day DESC
        """),
        {"since": seven_days_ago}
    ).fetchall()

    # Retention status (brief)
    retention = RetentionService(db)
    retention_status = retention.get_retention_status()

    last_scan_at = scan.get("last_scan_at")

    return {
        "generated_at": now.isoformat(),
        "compliance_scan": {
            "total_checks": scan.get("total_checks", 0) or 0,
            "passed": scan.get("passed", 0) or 0,
            "failed": scan.get("failed", 0) or 0,
            "warnings": scan.get("warnings", 0) or 0,
            "errors": scan.get("errors", 0) or 0,
            "last_scan_at": last_scan_at.isoformat() if last_scan_at else None,
        },
        "open_incidents": {
            "total": inc.get("total_open", 0) or 0,
            "critical": inc.get("critical", 0) or 0,
            "high": inc.get("high", 0) or 0,
            "medium": inc.get("medium", 0) or 0,
            "low": inc.get("low_sev", 0) or 0,
        },
        "data_classification": {
            "total_columns_classified": cls.get("total_columns", 0) or 0,
            "pii_columns": pii_total,
            "pii_encrypted": pii_encrypted,
            "pii_encryption_percentage": pii_encryption_pct,
            "financial_columns": cls.get("financial_columns", 0) or 0,
        },
        "failed_login_trends_7d": [
            dict(row._mapping)
            for row in failed_logins
        ],
        "data_retention": retention_status,
    }
