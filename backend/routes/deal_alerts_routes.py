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


# =============================================================================
# Admin Migration Endpoint
# =============================================================================

@router.get("/admin/debug-loans")
async def debug_loans_data(
    db: Session = Depends(get_db),
):
    """Debug endpoint to check loans data status."""
    try:
        from sqlalchemy import text

        # Check loan count by stage (cast to text to handle enum)
        result = db.execute(text("""
            SELECT stage::text as stage_name, COUNT(*) as count
            FROM loans
            GROUP BY stage
            ORDER BY count DESC
        """))
        stage_counts = [{"stage": row[0], "count": row[1]} for row in result.fetchall()]

        # Get total loan count
        total_result = db.execute(text("SELECT COUNT(*) FROM loans"))
        total_count = total_result.scalar()

        # Check columns in loans table
        columns_result = db.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'loans'
            ORDER BY ordinal_position
        """))
        columns = [{"name": row[0], "type": row[1]} for row in columns_result.fetchall()]

        # Get enum values if stage is an enum
        enum_result = db.execute(text("""
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'loanstage'
        """))
        enum_values = [row[0] for row in enum_result.fetchall()]

        # Get sample loans - only use columns we know exist
        sample = db.execute(text("""
            SELECT id, loan_number, stage::text, updated_at
            FROM loans
            LIMIT 3
        """))
        sample_loans = [dict(zip(['id', 'loan_number', 'stage', 'updated_at'], row)) for row in sample.fetchall()]

        return {
            "status": "success",
            "total_loans": total_count,
            "total_by_stage": stage_counts,
            "loans_table_columns": columns[:30],
            "stage_enum_values": enum_values,
            "sample_loans": sample_loans,
            "database_connected": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "database_connected": False
        }


@router.get("/admin/run-migration")
async def run_deal_alerts_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db),
):
    """
    Run the deal alerts database migration.
    Creates deal_alerts, whisper_sessions, whisper_messages, and production_forecasts tables.
    """
    import os
    expected_key = os.getenv("ADMIN_API_KEY", "perennia-admin-2024")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from sqlalchemy import text

        # Check if PostgreSQL or SQLite
        db_url = str(db.get_bind().url)
        is_postgres = 'postgresql' in db_url

        if is_postgres:
            # Create deal_alerts table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS deal_alerts (
                    id VARCHAR(50) PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    loan_id INTEGER REFERENCES loans(id),
                    loan_number VARCHAR(50),
                    borrower_name VARCHAR(255),
                    title VARCHAR(500) NOT NULL,
                    message TEXT,
                    details JSONB DEFAULT '{}',
                    recommended_action TEXT,
                    tags JSONB DEFAULT '[]',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    acknowledged_at TIMESTAMP WITH TIME ZONE,
                    acknowledged_by INTEGER REFERENCES users(id),
                    resolved_at TIMESTAMP WITH TIME ZONE,
                    resolved_by INTEGER REFERENCES users(id),
                    resolution_note TEXT,
                    snoozed_until TIMESTAMP WITH TIME ZONE,
                    due_date TIMESTAMP WITH TIME ZONE,
                    organization_id INTEGER,
                    user_id INTEGER REFERENCES users(id)
                )
            """))

            # Create indexes
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_status ON deal_alerts(status)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_priority ON deal_alerts(priority)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_loan_id ON deal_alerts(loan_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_type ON deal_alerts(type)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_org ON deal_alerts(organization_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_user ON deal_alerts(user_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_deal_alerts_created ON deal_alerts(created_at DESC)"))

            # Create whisper_sessions table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_sessions (
                    id VARCHAR(50) PRIMARY KEY,
                    call_id VARCHAR(100),
                    user_id INTEGER REFERENCES users(id),
                    contact_id INTEGER,
                    contact_name VARCHAR(255),
                    contact_type VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'active',
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ended_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    whisper_count INTEGER DEFAULT 0,
                    ai_suggestions_count INTEGER DEFAULT 0,
                    organization_id INTEGER
                )
            """))

            # Create whisper_messages table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS whisper_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(50) REFERENCES whisper_sessions(id),
                    message_type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) DEFAULT 'medium',
                    content TEXT NOT NULL,
                    context JSONB,
                    source VARCHAR(20) DEFAULT 'ai',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    acknowledged_at TIMESTAMP WITH TIME ZONE
                )
            """))

            db.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_sessions_user ON whisper_sessions(user_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_sessions_status ON whisper_sessions(status)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_whisper_messages_session ON whisper_messages(session_id)"))

            # Create production_forecasts table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS production_forecasts (
                    id SERIAL PRIMARY KEY,
                    entity_type VARCHAR(20) NOT NULL,
                    entity_id INTEGER NOT NULL,
                    forecast_date DATE NOT NULL,
                    period_days INTEGER NOT NULL,
                    predicted_units INTEGER,
                    predicted_volume NUMERIC(15, 2),
                    confidence NUMERIC(5, 4),
                    actual_units INTEGER,
                    actual_volume NUMERIC(15, 2),
                    model_version VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    organization_id INTEGER
                )
            """))

            db.execute(text("CREATE INDEX IF NOT EXISTS idx_prod_forecasts_entity ON production_forecasts(entity_type, entity_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_prod_forecasts_date ON production_forecasts(forecast_date)"))
        else:
            # SQLite version
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS deal_alerts (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'active',
                    loan_id INTEGER REFERENCES loans(id),
                    loan_number TEXT,
                    borrower_name TEXT,
                    title TEXT NOT NULL,
                    message TEXT,
                    details TEXT,
                    recommended_action TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP,
                    acknowledged_by INTEGER REFERENCES users(id),
                    resolved_at TIMESTAMP,
                    resolved_by INTEGER REFERENCES users(id),
                    resolution_note TEXT,
                    snoozed_until TIMESTAMP,
                    due_date TIMESTAMP,
                    organization_id INTEGER,
                    user_id INTEGER REFERENCES users(id)
                )
            """))

        db.commit()

        return {
            "status": "success",
            "message": "Deal alerts migration completed successfully",
            "tables_created": ["deal_alerts", "whisper_sessions", "whisper_messages", "production_forecasts"],
            "database_type": "postgresql" if is_postgres else "sqlite"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
