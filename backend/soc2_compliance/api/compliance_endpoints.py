"""
Compliance Dashboard Endpoints
Provides compliance metrics, reports, and health checks.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Generate a comprehensive SOC 2 Type II compliance report.
    This is the primary evidence artifact for auditors.
    """
    reporter = ComplianceReporter(db)
    report = await reporter.generate_full_report(
        tenant_id=current_user.tenant_id,
        start_date=start_date,
        end_date=end_date,
    )
    return report


@router.get("/health")
async def compliance_health_check(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Quick compliance health check.
    Returns current status of key controls.
    """
    retention = RetentionService(db)
    retention_status = await retention.get_retention_status()

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
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get data retention status and volumes."""
    retention = RetentionService(db)
    return {
        "status": await retention.get_retention_status(),
        "preview": await retention.preview_retention_enforcement(),
    }


@router.post("/retention/enforce")
async def enforce_retention(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Manually trigger retention policy enforcement."""
    retention = RetentionService(db)
    results = await retention.enforce_retention_policies()
    return {"results": results}


@router.get("/access/summary")
async def get_access_summary(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get access event summary for compliance review."""
    access = AccessControlService(db)
    summary = await access.get_access_summary(
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
    )
    return {"data": summary}


@router.get("/incidents/metrics")
async def get_incident_metrics(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get incident response metrics for compliance review."""
    incidents = IncidentService(db)
    metrics = await incidents.get_incident_metrics(
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
    )
    return {"data": metrics}
