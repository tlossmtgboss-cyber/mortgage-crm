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
from sqlalchemy.exc import SQLAlchemyError
from services.proactive_deal_alerts_service import (
    ProactiveDealAlertsService,
    get_deal_alerts_service,
    AlertType,
    AlertPriority,
    AlertStatus,
    DealAlert,
)

logger = logging.getLogger(__name__)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/deal-alerts",
    tags=["Deal Alerts"],
    dependencies=[Depends(_get_current_user())],
)


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=400, detail="Invalid filter value")
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Admin Migration Endpoint
# =============================================================================

@router.get("/admin/test-funded")
async def test_funded_loans(
    db: Session = Depends(get_db),
):
    """Test funded loans query for production predictor."""
    try:
        from sqlalchemy import text

        # Check funded loans with dates
        result = db.execute(text("""
            SELECT
                l.id,
                l.loan_number,
                l.stage::text as stage,
                l.funded_date,
                l.amount
            FROM loans l
            WHERE UPPER(l.stage::text) = 'FUNDED'
            ORDER BY l.funded_date DESC NULLS LAST
            LIMIT 10
        """))

        loans = [dict(zip(['id', 'loan_number', 'stage', 'funded_date', 'amount'], row)) for row in result.fetchall()]

        # Format dates
        for loan in loans:
            if loan['funded_date']:
                loan['funded_date'] = str(loan['funded_date'])

        return {
            "status": "success",
            "funded_loans": loans,
            "count": len(loans)
        }
    except Exception as e:
        import traceback
        return {"status": "error", "error": "Internal server error"}


@router.get("/admin/test-predictor-query")
async def test_predictor_query(
    entity_id: str = "57",
    db: Session = Depends(get_db),
):
    """Test the exact production predictor query."""
    try:
        from sqlalchemy import text

        # Same query as production predictor service
        result = db.execute(text("""
            SELECT
                DATE_TRUNC('month', l.funded_date) as month,
                COUNT(*) as units,
                COALESCE(SUM(l.amount), 0) as volume
            FROM loans l
            LEFT JOIN users u ON l.loan_officer_id = u.id
            WHERE l.funded_date >= CURRENT_DATE - INTERVAL '12 months'
                AND UPPER(l.stage::text) = 'FUNDED'
                AND l.loan_officer_id = :entity_id
            GROUP BY DATE_TRUNC('month', l.funded_date)
            ORDER BY month ASC
        """), {"entity_id": entity_id})

        rows = result.fetchall()
        data = []
        for row in rows:
            data.append({
                "month": str(row[0]) if row[0] else None,
                "units": row[1],
                "volume": float(row[2]) if row[2] else 0
            })

        return {
            "status": "success",
            "entity_id": entity_id,
            "months_found": len(data),
            "data": data
        }
    except Exception as e:
        import traceback
        return {"status": "error", "error": "Internal server error"}


@router.get("/admin/test-query")
async def test_loan_query(
    db: Session = Depends(get_db),
):
    """Test the exact query used by _get_sample_loans() to debug why it fails."""
    try:
        from sqlalchemy import text
        from datetime import date, timedelta
        today = date.today()

        # Run the exact query from _get_sample_loans() - fixed columns
        result = db.execute(text("""
            SELECT
                l.id,
                COALESCE(l.loan_number, 'LOAN-' || l.id) as loan_number,
                COALESCE(l.borrower_name, 'Unknown') as borrower_name,
                COALESCE(l.stage::text, 'processing') as status,
                COALESCE(l.days_in_stage, EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.updated_at))::integer, 0) as days_in_stage,
                l.amount as loan_amount
            FROM loans l
            WHERE l.stage IS NULL
               OR UPPER(l.stage::text) NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'CLOSED')
            ORDER BY l.updated_at ASC
            LIMIT 20
        """))

        rows = result.fetchall()
        loans = []
        for row in rows:
            row_dict = row._asdict() if hasattr(row, '_asdict') else dict(zip(['id', 'loan_number', 'borrower_name', 'status', 'days_in_stage', 'loan_amount'], row))
            loans.append({
                "id": str(row_dict.get('id')),
                "loan_number": row_dict.get('loan_number'),
                "borrower_name": row_dict.get('borrower_name'),
                "status": row_dict.get('status'),
                "days_in_stage": row_dict.get('days_in_stage'),
                "loan_amount": float(row_dict.get('loan_amount') or 0),
            })

        return {
            "status": "success",
            "query_returned": len(loans),
            "loans": loans,
            "message": "Query executed successfully" if loans else "Query returned no results"
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": "Internal server error"
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
    expected_key = os.getenv("ADMIN_API_KEY", "")
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

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")


@router.post("/seed-sample-alerts")
async def seed_sample_alerts(db: Session = Depends(get_db)):
    """
    Seed sample deal alerts for testing and demo purposes.
    Creates a variety of alerts with different priorities and types.
    """
    import uuid
    from datetime import datetime, timedelta

    try:
        service = get_deal_alerts_service(db_session=db)

        # Sample alerts data
        sample_alerts = [
            {
                "type": AlertType.RATE_LOCK_EXPIRING,
                "priority": AlertPriority.CRITICAL,
                "loan_number": "2025-001234",
                "borrower_name": "John & Sarah Martinez",
                "title": "Rate Lock Expiring in 3 Days",
                "message": "Rate lock for the Martinez loan expires on January 14th. Current rate: 6.25%. Market rate: 6.50%.",
                "recommended_action": "Contact borrower to confirm closing timeline or discuss lock extension options",
                "due_date": datetime.now().date() + timedelta(days=3),
                "tags": ["rate_lock", "urgent", "closing_soon"],
            },
            {
                "type": AlertType.STALLED_LOAN,
                "priority": AlertPriority.HIGH,
                "loan_number": "2025-001189",
                "borrower_name": "Michael Thompson",
                "title": "Loan Stalled in Processing - 12 Days",
                "message": "No activity for 12 days. Last update: Waiting on bank statements from borrower.",
                "recommended_action": "Follow up with borrower on outstanding documents. Consider escalating to manager.",
                "due_date": datetime.now().date(),
                "tags": ["stalled", "documents_needed", "follow_up"],
            },
            {
                "type": AlertType.DOCUMENT_EXPIRING,
                "priority": AlertPriority.MEDIUM,
                "loan_number": "2025-001156",
                "borrower_name": "Emily Chen",
                "title": "Credit Report Expiring in 7 Days",
                "message": "Credit report will expire before scheduled closing. New pull may affect approval.",
                "recommended_action": "Expedite closing or prepare for credit refresh with underwriting",
                "due_date": datetime.now().date() + timedelta(days=7),
                "tags": ["credit", "expiring", "underwriting"],
            },
            {
                "type": AlertType.COMPLIANCE_DEADLINE,
                "priority": AlertPriority.HIGH,
                "loan_number": "2025-001201",
                "borrower_name": "Robert & Lisa Williams",
                "title": "CD Due Tomorrow - Not Yet Sent",
                "message": "Closing Disclosure must be sent by tomorrow to maintain compliance. Closing scheduled for Jan 15.",
                "recommended_action": "Immediately prepare and send Closing Disclosure to borrower",
                "due_date": datetime.now().date() + timedelta(days=1),
                "tags": ["compliance", "trid", "cd", "urgent"],
            },
            {
                "type": AlertType.APPRAISAL_ISSUE,
                "priority": AlertPriority.HIGH,
                "loan_number": "2025-001178",
                "borrower_name": "David Park",
                "title": "Appraisal Came in $25K Under Contract",
                "message": "Property appraised at $475,000 vs $500,000 contract price. LTV now exceeds program limits.",
                "recommended_action": "Discuss options with borrower: renegotiate price, bring cash to close, or contest appraisal",
                "due_date": datetime.now().date() + timedelta(days=2),
                "tags": ["appraisal", "value", "ltv", "negotiation"],
            },
            {
                "type": AlertType.SLA_AT_RISK,
                "priority": AlertPriority.MEDIUM,
                "loan_number": "2025-001145",
                "borrower_name": "Jennifer Adams",
                "title": "Processing SLA at Risk",
                "message": "Loan has been in processing for 4 days. SLA target is 5 days.",
                "recommended_action": "Review file status and ensure all conditions are being actively worked",
                "due_date": datetime.now().date() + timedelta(days=1),
                "tags": ["sla", "processing", "timeline"],
            },
            {
                "type": AlertType.BORROWER_UNRESPONSIVE,
                "priority": AlertPriority.MEDIUM,
                "loan_number": "2025-001167",
                "borrower_name": "Chris & Amanda Brown",
                "title": "Borrower Unresponsive - 5 Days",
                "message": "No response to 3 calls and 2 emails requesting employment verification letter.",
                "recommended_action": "Try alternate contact method or reach out to real estate agent",
                "due_date": datetime.now().date(),
                "tags": ["communication", "borrower", "documents"],
            },
            {
                "type": AlertType.CLOSING_DELAY_RISK,
                "priority": AlertPriority.LOW,
                "loan_number": "2025-001190",
                "borrower_name": "Michelle Garcia",
                "title": "Potential Closing Delay - Title Issue",
                "message": "Title company found old lien that needs to be cleared. May add 2-3 days to timeline.",
                "recommended_action": "Monitor title clearance progress and communicate potential delay to all parties",
                "due_date": datetime.now().date() + timedelta(days=5),
                "tags": ["title", "lien", "closing", "delay"],
            },
        ]

        created_count = 0
        for alert_data in sample_alerts:
            alert = DealAlert(
                id=str(uuid.uuid4()),
                type=alert_data["type"],
                priority=alert_data["priority"],
                status=AlertStatus.ACTIVE,
                loan_id=str(uuid.uuid4()),
                loan_number=alert_data["loan_number"],
                borrower_name=alert_data["borrower_name"],
                title=alert_data["title"],
                message=alert_data["message"],
                details={"source": "sample_data", "created_by": "seed_script"},
                recommended_action=alert_data["recommended_action"],
                created_at=datetime.now() - timedelta(hours=created_count * 2),
                due_date=alert_data.get("due_date"),
                tags=alert_data.get("tags", []),
            )
            service._alerts[alert.id] = alert
            created_count += 1

        return {
            "status": "success",
            "message": f"Created {created_count} sample deal alerts",
            "alerts_created": created_count,
            "alert_types": list(set(a["type"].value for a in sample_alerts)),
        }

    except Exception as e:
        logger.error(f"Error seeding sample alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
