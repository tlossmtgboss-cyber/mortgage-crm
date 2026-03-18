"""
Pipeline Trigger Failure Management
====================================
Endpoints for LOs to view and acknowledge AI scheduling failures.

Endpoints:
  GET  /pipeline-triggers/failures                      List recent trigger failures for current LO
  POST /pipeline-triggers/failures/{failure_id}/acknowledge  Mark a failure as acknowledged
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import logging

from db import get_db
from routes.scheduler._helpers import get_current_user, _get_org_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Pipeline Triggers"])


@router.get("/pipeline-triggers/failures")
async def get_trigger_failures(
    request: Request,
    limit: int = 10,
    status: str = "unacknowledged",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get recent pipeline trigger failures for the current LO.

    Args:
        limit: Max number of failures to return (default 10).
        status: Filter mode — "unacknowledged" (default) or "all".
    """
    user_id = user.id
    org_id = _get_org_id(user)

    # Query PipelineAppointmentTriggerLog for failures
    # Table: pipeline_appointment_trigger_log (singular)
    # Columns: action_taken, error_message, status (not "action"/"error")
    query = text("""
        SELECT
            t.id, t.loan_id, t.appointment_type, t.appointment_title,
            t.action_taken, t.error_message, t.status, t.created_at,
            t.old_stage, t.new_stage, t.acknowledged_at,
            l.loan_number, l.borrower_name
        FROM pipeline_appointment_trigger_log t
        LEFT JOIN loans l ON l.id = t.loan_id
        WHERE t.status = 'failed'
            AND t.loan_officer_id = :user_id
            AND t.organization_id = :org_id
            AND (:status = 'all' OR t.acknowledged_at IS NULL)
        ORDER BY t.created_at DESC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "user_id": user_id,
        "org_id": org_id,
        "status": status,
        "limit": limit,
    }).fetchall()

    return {
        "failures": [
            {
                "id": r.id,
                "loan_id": r.loan_id,
                "loan_number": r.loan_number,
                "borrower_name": r.borrower_name,
                "appointment_type": r.appointment_type,
                "appointment_title": r.appointment_title,
                "action_taken": r.action_taken,
                "error": r.error_message,
                "old_stage": r.old_stage,
                "new_stage": r.new_stage,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                "message": f"Failed to schedule {r.appointment_title or r.appointment_type} for {r.borrower_name or r.loan_number or 'unknown borrower'}",
            }
            for r in results
        ],
        "count": len(results),
    }


@router.post("/pipeline-triggers/failures/{failure_id}/acknowledge")
async def acknowledge_trigger_failure(
    failure_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Acknowledge a pipeline trigger failure so it no longer appears in the unacknowledged list."""
    org_id = _get_org_id(user)

    # Verify the failure belongs to this LO and org before updating
    result = db.execute(
        text("""
            UPDATE pipeline_appointment_trigger_log
            SET acknowledged_at = :now
            WHERE id = :id
                AND loan_officer_id = :user_id
                AND organization_id = :org_id
                AND acknowledged_at IS NULL
        """),
        {
            "now": datetime.now(timezone.utc),
            "id": failure_id,
            "user_id": user.id,
            "org_id": org_id,
        },
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Failure not found, already acknowledged, or not owned by current user",
        )

    return {"status": "acknowledged", "failure_id": failure_id}
