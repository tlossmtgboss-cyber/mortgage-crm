"""
Proactive Deal Alerts Routes

API endpoints for deal monitoring and alerting.
Part of the Pipeline Management / Advanced Analytics module.
"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.proactive_deal_alerts_service import (
    ProactiveDealAlertsService,
    get_deal_alerts_service,
    AlertType,
    AlertPriority,
    AlertStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/deal-alerts", tags=["Deal Alerts"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AlertResponse(BaseModel):
    """Single alert response."""
    id: str
    type: str
    priority: str
    status: str
    loan_id: str
    loan_number: str
    borrower_name: str
    title: str
    message: str
    details: dict
    recommended_action: str
    created_at: str
    due_date: Optional[str]
    tags: List[str]


class AlertSummaryResponse(BaseModel):
    """Alert summary response."""
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    by_type: dict
    loans_at_risk: int
    alerts_today: int
    resolved_today: int


class BulkAcknowledgeRequest(BaseModel):
    """Request to acknowledge multiple alerts."""
    alert_ids: List[str]


class SnoozeRequest(BaseModel):
    """Request to snooze an alert."""
    snooze_hours: int = Field(default=24, ge=1, le=168)


class ResolveRequest(BaseModel):
    """Request to resolve an alert."""
    resolution_note: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/scan")
async def scan_pipeline(
    user_id: Optional[str] = Query(default=None),
    branch_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Scan the pipeline and generate new alerts.

    This triggers a full scan of all active loans to identify
    potential issues and generate proactive alerts.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alerts = service.scan_pipeline(user_id=user_id, branch_id=branch_id)

        return {
            "status": "complete",
            "alerts_generated": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
            "scanned_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error scanning pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(
    user_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Get summary of current alerts.

    Returns counts by priority and type.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        summary = service.get_summary(user_id=user_id)

        return AlertSummaryResponse(
            total_alerts=summary.total_alerts,
            critical_count=summary.critical_count,
            high_count=summary.high_count,
            medium_count=summary.medium_count,
            low_count=summary.low_count,
            by_type=summary.by_type,
            loans_at_risk=summary.loans_at_risk,
            alerts_today=summary.alerts_today,
            resolved_today=summary.resolved_today,
        )
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[AlertResponse])
async def get_alerts(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    priority: Optional[str] = Query(default=None, description="Filter by priority"),
    alert_type: Optional[str] = Query(default=None, description="Filter by type"),
    loan_id: Optional[str] = Query(default=None, description="Filter by loan"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Get list of alerts with optional filters.
    """
    try:
        service = get_deal_alerts_service(db_session=db)

        # Convert string filters to enums
        status_enum = AlertStatus(status) if status else None
        priority_enum = AlertPriority(priority) if priority else None
        type_enum = AlertType(alert_type) if alert_type else None

        alerts = service.get_alerts(
            status=status_enum,
            priority=priority_enum,
            alert_type=type_enum,
            loan_id=loan_id,
        )[:limit]

        return [
            AlertResponse(
                id=a.id,
                type=a.type.value,
                priority=a.priority.value,
                status=a.status.value,
                loan_id=a.loan_id,
                loan_number=a.loan_number,
                borrower_name=a.borrower_name,
                title=a.title,
                message=a.message,
                details=a.details,
                recommended_action=a.recommended_action,
                created_at=a.created_at.isoformat(),
                due_date=a.due_date.isoformat() if a.due_date else None,
                tags=a.tags,
            )
            for a in alerts
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {e}")
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/priority-actions")
async def get_priority_actions(
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Get top priority actions that need immediate attention.

    Returns a list of the most critical actions to take.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        actions = service.get_priority_actions(limit=limit)
        return {"priority_actions": actions}
    except Exception as e:
        logger.error(f"Error getting priority actions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
async def get_alert_types():
    """
    Get list of all alert types.
    """
    return {
        "alert_types": [t.value for t in AlertType],
        "priorities": [p.value for p in AlertPriority],
        "statuses": [s.value for s in AlertStatus],
    }


@router.get("/health")
async def alerts_health(db: Session = Depends(get_db)):
    """Health check for the deal alerts service."""
    service = get_deal_alerts_service(db_session=db)
    summary = service.get_summary()

    return {
        "status": "healthy",
        "service": "deal-alerts",
        "active_alerts": summary.total_alerts,
        "critical_alerts": summary.critical_count,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/loan/{loan_id}")
async def get_alerts_for_loan(loan_id: str, db: Session = Depends(get_db)):
    """
    Get all alerts for a specific loan.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alerts = service.get_alerts_for_loan(loan_id)

        return {
            "loan_id": loan_id,
            "alert_count": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
        }
    except Exception as e:
        logger.error(f"Error getting loan alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Dynamic routes with {alert_id} path parameter MUST be after all static routes
@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Get a specific alert by ID.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alert = service.get_alert(alert_id)

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return AlertResponse(
            id=alert.id,
            type=alert.type.value,
            priority=alert.priority.value,
            status=alert.status.value,
            loan_id=alert.loan_id,
            loan_number=alert.loan_number,
            borrower_name=alert.borrower_name,
            title=alert.title,
            message=alert.message,
            details=alert.details,
            recommended_action=alert.recommended_action,
            created_at=alert.created_at.isoformat(),
            due_date=alert.due_date.isoformat() if alert.due_date else None,
            tags=alert.tags,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Acknowledge an alert.

    Indicates the user has seen the alert and is aware of the issue.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alert = service.acknowledge_alert(alert_id)

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return {
            "status": "acknowledged",
            "alert_id": alert_id,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: ResolveRequest, db: Session = Depends(get_db)):
    """
    Resolve an alert.

    Indicates the underlying issue has been addressed.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alert = service.resolve_alert(alert_id, request.resolution_note)

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return {
            "status": "resolved",
            "alert_id": alert_id,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/snooze")
async def snooze_alert(alert_id: str, request: SnoozeRequest, db: Session = Depends(get_db)):
    """
    Snooze an alert for a specified duration.

    The alert will reappear after the snooze period.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        alert = service.snooze_alert(alert_id, request.snooze_hours)

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        return {
            "status": "snoozed",
            "alert_id": alert_id,
            "snoozed_until": alert.snoozed_until.isoformat() if alert.snoozed_until else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error snoozing alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-acknowledge")
async def bulk_acknowledge(request: BulkAcknowledgeRequest, db: Session = Depends(get_db)):
    """
    Acknowledge multiple alerts at once.
    """
    try:
        service = get_deal_alerts_service(db_session=db)
        count = service.bulk_acknowledge(request.alert_ids)

        return {
            "status": "acknowledged",
            "acknowledged_count": count,
            "requested_count": len(request.alert_ids),
        }
    except Exception as e:
        logger.error(f"Error bulk acknowledging: {e}")
        raise HTTPException(status_code=500, detail=str(e))
