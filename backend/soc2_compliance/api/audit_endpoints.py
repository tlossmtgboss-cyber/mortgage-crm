"""
Audit Log Query Endpoints
Provides read-only access to audit trails for compliance review.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.audit_service import AuditService
from .dependencies import get_soc2_db as get_db, get_current_admin_user

router = APIRouter()


@router.get("/logs")
async def query_audit_logs(
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_time: Optional[datetime] = Query(None, description="Start of time range"),
    end_time: Optional[datetime] = Query(None, description="End of time range"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Query audit logs with filters.
    Requires admin role. Results are scoped to the user's tenant.
    """
    audit = AuditService(db)
    tenant_id = getattr(current_user, "tenant_id", None)

    logs = await audit.query_logs(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return {"data": logs, "count": len(logs), "limit": limit, "offset": offset}


@router.get("/logs/summary")
async def get_audit_summary(
    start_time: datetime = Query(..., description="Start of reporting period"),
    end_time: datetime = Query(..., description="End of reporting period"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get audit event summary for a time period."""
    audit = AuditService(db)
    tenant_id = getattr(current_user, "tenant_id", None)

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    summary = await audit.get_audit_summary(tenant_id, start_time, end_time)
    return {"data": summary}


@router.get("/logs/resource/{resource_type}/{resource_id}")
async def get_resource_audit_trail(
    resource_type: str,
    resource_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get complete audit trail for a specific resource (e.g., a loan application)."""
    audit = AuditService(db)
    tenant_id = getattr(current_user, "tenant_id", None)

    logs = await audit.query_logs(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
    )

    return {"data": logs, "resource_type": resource_type, "resource_id": resource_id}
