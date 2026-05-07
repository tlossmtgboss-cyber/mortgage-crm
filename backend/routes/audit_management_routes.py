"""
Audit Management Admin Routes

Admin-only endpoints for audit log lifecycle management.

Endpoints:
    POST /api/v1/admin/audit/cleanup — Delete audit entries older than retention period
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user_flexible
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/audit", tags=["Audit Management"])


class AuditCleanupRequest(BaseModel):
    retention_days: int = Field(
        default=2555,
        ge=365,
        description="Number of days to retain. Minimum 365 (1 year). Default 2555 (~7 years).",
    )


class AuditCleanupResponse(BaseModel):
    deleted: int
    cutoff_date: str
    retention_days: int
    message: str


def _require_platform_admin(user) -> None:
    """Raise 403 if the user is not a platform admin."""
    role = getattr(user, "role", None)
    if role not in ("platform_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Platform admin access required")


@router.post("/cleanup", response_model=AuditCleanupResponse)
async def audit_cleanup(
    request: Request,
    body: AuditCleanupRequest = AuditCleanupRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible),
):
    """Delete audit log entries older than the retention period.

    Requires platform_admin or super_admin role. Default retention is 2555 days
    (~7 years) to satisfy RESPA/TILA mortgage record-keeping requirements.
    """
    _require_platform_admin(current_user)

    from services.audit_service import cleanup_old_audit_events

    try:
        result = cleanup_old_audit_events(db, retention_days=body.retention_days)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Audit cleanup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Audit cleanup failed")

    logger.info(
        f"Audit cleanup by user {getattr(current_user, 'id', '?')}: "
        f"deleted={result['deleted']}, retention_days={body.retention_days}"
    )

    return AuditCleanupResponse(**result)
