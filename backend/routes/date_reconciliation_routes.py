"""
Date Reconciliation API Routes

Provides endpoints for:
- Viewing pending date reconciliation tasks
- Resolving reconciliation tasks by linking loans
- Getting date update history
- Manually triggering date sync
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from db import get_async_db

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class ResolveReconciliationRequest(BaseModel):
    """Request to resolve a reconciliation task."""
    task_id: int
    loan_id: int
    salesforce_id: str


class CreateLoanFromReconciliationRequest(BaseModel):
    """Request to create a new loan from a reconciliation task."""
    task_id: int
    borrower_name: str
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    loan_number: Optional[str] = None
    salesforce_id: str


class DateUpdateHistoryItem(BaseModel):
    """A date update history entry."""
    id: int
    field_name: str
    old_value: Optional[str]
    new_value: str
    update_source: str
    updated_at: datetime


# =============================================================================
# Runtime imports to avoid circular dependencies
# =============================================================================

def get_current_user_dep():
    """Get current user - imports from main at runtime."""
    import main
    return main.get_current_user


def get_date_reconciliation_service(db: AsyncSession, user_id: int):
    """Get the date reconciliation service."""
    from services.date_reconciliation_service import DateReconciliationService
    return DateReconciliationService(db, user_id)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/pending")
async def get_pending_date_reconciliation_tasks(
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all pending date reconciliation tasks.

    These are tasks created when Salesforce date updates couldn't be matched
    to existing loans/borrowers in the CRM.
    """
    try:
        service = get_date_reconciliation_service(db, current_user.id)
        tasks = service.get_pending_date_reconciliation_tasks()

        return {
            "status": "success",
            "count": len(tasks),
            "tasks": tasks
        }
    except Exception as e:
        logger.error(f"Error getting pending date reconciliation tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/all")
async def get_all_date_reconciliation_tasks(
    status: Optional[str] = Query(None, description="Filter by status: pending, completed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get all date reconciliation tasks with optional filtering.
    """
    try:
        params = {"owner_id": current_user.id, "limit": limit, "offset": offset}
        status_filter = ""

        if status:
            status_filter = "AND status = :status"
            params["status"] = status

        query = (
            "SELECT id, title, description, status, priority, created_at, completed_at"
            " FROM tasks"
            " WHERE source = 'Salesforce Date Sync'"
            " AND owner_id = :owner_id"
            " " + status_filter +
            " ORDER BY created_at DESC"
            " LIMIT :limit OFFSET :offset"
        )
        result = await db.execute(text(query), params)

        tasks = [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "status": row[3],
                "priority": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "completed_at": row[6].isoformat() if row[6] else None,
            }
            for row in result.fetchall()
        ]

        # Get total count
        count_query = (
            "SELECT COUNT(*) FROM tasks"
            " WHERE source = 'Salesforce Date Sync'"
            " AND owner_id = :owner_id"
            " " + status_filter
        )
        count_result = await db.execute(text(count_query), params)
        total = count_result.scalar()

        return {
            "status": "success",
            "count": len(tasks),
            "total": total,
            "tasks": tasks
        }
    except Exception as e:
        logger.error(f"Error getting date reconciliation tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/resolve")
async def resolve_reconciliation_task(
    request: ResolveReconciliationRequest,
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resolve a date reconciliation task by linking a loan to the Salesforce record.

    This will:
    1. Link the loan to the Salesforce record ID
    2. Mark the reconciliation task as completed
    3. Trigger a re-sync of the date fields
    """
    try:
        service = get_date_reconciliation_service(db, current_user.id)

        # Verify the task exists and belongs to user
        task = (await db.execute(text("""
            SELECT id, status FROM tasks
            WHERE id = :task_id
              AND owner_id = :owner_id
              AND source = 'Salesforce Date Sync'
        """), {"task_id": request.task_id, "owner_id": current_user.id})).fetchone()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task[1] == "completed":
            raise HTTPException(status_code=400, detail="Task is already completed")

        # Verify the loan exists
        loan = (await db.execute(text("""
            SELECT id, loan_number, borrower_name FROM loans WHERE id = :loan_id
        """), {"loan_id": request.loan_id})).fetchone()

        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Resolve the task
        success = service.resolve_reconciliation_task(
            task_id=request.task_id,
            loan_id=request.loan_id,
            salesforce_id=request.salesforce_id,
        )

        if success:
            return {
                "status": "success",
                "message": f"Linked loan {loan[1] or loan[0]} to Salesforce record",
                "loan_id": request.loan_id,
                "loan_number": loan[1],
                "borrower_name": loan[2],
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to resolve task")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving reconciliation task: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create-loan")
async def create_loan_from_reconciliation(
    request: CreateLoanFromReconciliationRequest,
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new loan from a date reconciliation task.

    This will:
    1. Create a new loan record with the provided borrower info
    2. Link it to the Salesforce record
    3. Mark the reconciliation task as completed
    """
    try:
        # Verify the task exists
        task = (await db.execute(text("""
            SELECT id, description FROM tasks
            WHERE id = :task_id
              AND owner_id = :owner_id
              AND source = 'Salesforce Date Sync'
              AND status = 'pending'
        """), {"task_id": request.task_id, "owner_id": current_user.id})).fetchone()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found or already completed")

        # Generate loan number if not provided
        loan_number = request.loan_number
        if not loan_number:
            import random
            loan_number = f"SF-{request.salesforce_id[-8:]}"

        # Create the loan
        result = await db.execute(text("""
            INSERT INTO loans (
                loan_number, borrower_name, borrower_email, borrower_phone,
                salesforce_id, salesforce_sync_status, loan_officer_id,
                stage, sla_status, created_at, updated_at
            ) VALUES (
                :loan_number, :borrower_name, :borrower_email, :borrower_phone,
                :sf_id, 'linked', :lo_id,
                'PROCESSING', 'on-track', NOW(), NOW()
            ) RETURNING id
        """), {
            "loan_number": loan_number,
            "borrower_name": request.borrower_name,
            "borrower_email": request.borrower_email,
            "borrower_phone": request.borrower_phone,
            "sf_id": request.salesforce_id,
            "lo_id": current_user.id,
        })

        new_loan_id = result.scalar()

        # Mark task as completed
        await db.execute(text("""
            UPDATE tasks
            SET status = 'completed',
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = :task_id
        """), {"task_id": request.task_id})

        await db.commit()

        logger.info(f"Created loan {new_loan_id} from reconciliation task {request.task_id}")

        return {
            "status": "success",
            "message": f"Created loan {loan_number} and linked to Salesforce",
            "loan_id": new_loan_id,
            "loan_number": loan_number,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating loan from reconciliation: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/date-history/{loan_id}")
async def get_loan_date_update_history(
    loan_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get date update history for a specific loan.

    Shows all date field changes tracked during Salesforce syncs.
    """
    try:
        # Verify loan access
        loan = (await db.execute(text("""
            SELECT id, loan_number, borrower_name FROM loans WHERE id = :loan_id
        """), {"loan_id": loan_id})).fetchone()

        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Get field update history
        result = await db.execute(text("""
            SELECT id, field_name, old_value, new_value, update_source, updated_at
            FROM field_update_history
            WHERE entity_type = 'loan'
              AND entity_id = :loan_id
              AND field_name LIKE '%date%'
            ORDER BY updated_at DESC
            LIMIT :limit
        """), {"loan_id": loan_id, "limit": limit})

        history = [
            {
                "id": row[0],
                "field_name": row[1],
                "old_value": row[2],
                "new_value": row[3],
                "update_source": row[4],
                "updated_at": row[5].isoformat() if row[5] else None,
            }
            for row in result.fetchall()
        ]

        return {
            "status": "success",
            "loan_id": loan_id,
            "loan_number": loan[1],
            "borrower_name": loan[2],
            "count": len(history),
            "history": history
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting date update history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/date-mappings")
async def get_date_field_mappings(
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the list of date fields that are tracked during Salesforce sync.

    These are the "custom byte mappings" - the date fields from Jungo/Salesforce
    that are synced to the CRM.
    """
    try:
        from services.date_reconciliation_service import DATE_FIELDS
        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING

        # Get date field mappings with Salesforce field names
        date_mappings = []
        for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
            if transform == "date" and crm_field in DATE_FIELDS:
                date_mappings.append({
                    "salesforce_field": sf_field,
                    "crm_field": crm_field,
                    "label": crm_field.replace("_", " ").title(),
                })

        # Group by category
        categories = {
            "lead_application": [
                "prospect_date", "application_date", "le_pending_date",
                "credit_only_date", "file_received_date", "preapproval_date"
            ],
            "lock": ["lock_date", "lock_expiration_date"],
            "processing_underwriting": [
                "uw_received_date", "conditions_for_review_date", "suspended_date",
                "loan_approved_date", "approved_not_accepted_date", "approval_expires_date"
            ],
            "appraisal": [
                "appraisal_ordered_date", "appraisal_received_date", "appraisal_docs_expire_date"
            ],
            "closing_disclosure": [
                "cd_requested_date", "cd_sent_to_borrower_date", "cd_acknowledged_date"
            ],
            "clear_to_close": [
                "clear_to_close_date", "docs_ordered_date", "docs_out_date", "credit_docs_expire_date"
            ],
            "funding": [
                "scheduled_closing_date", "scheduled_funding_date", "funds_ordered_date",
                "funds_sent_date", "funded_date", "closing_date", "first_payment_date"
            ],
            "post_closing": ["investor_purchased_date"],
            "status_changes": ["withdrawn_date", "contract_received_date"],
        }

        categorized = {}
        for category, fields in categories.items():
            categorized[category] = [
                m for m in date_mappings if m["crm_field"] in fields
            ]

        return {
            "status": "success",
            "total_date_fields": len(date_mappings),
            "mappings": date_mappings,
            "by_category": categorized,
        }

    except Exception as e:
        logger.error(f"Error getting date field mappings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summary")
async def get_date_reconciliation_summary(
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a summary of date reconciliation activity.

    Shows counts of pending tasks, recent updates, and sync status.
    """
    try:
        # Get pending task count
        pending_count = (await db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE source = 'Salesforce Date Sync'
              AND status = 'pending'
              AND owner_id = :owner_id
        """), {"owner_id": current_user.id})).scalar()

        # Get completed task count (last 30 days)
        completed_count = (await db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE source = 'Salesforce Date Sync'
              AND status = 'completed'
              AND owner_id = :owner_id
              AND completed_at >= NOW() - INTERVAL '30 days'
        """), {"owner_id": current_user.id})).scalar()

        # Get recent date updates count
        recent_updates = (await db.execute(text("""
            SELECT COUNT(*) FROM field_update_history
            WHERE entity_type = 'loan'
              AND field_name LIKE '%date%'
              AND update_source = 'salesforce_sync'
              AND updated_at >= NOW() - INTERVAL '7 days'
        """))).scalar() or 0

        # Get last sync time
        last_sync = (await db.execute(text("""
            SELECT MAX(salesforce_last_synced_at) FROM loans
            WHERE salesforce_id IS NOT NULL
        """))).scalar()

        return {
            "status": "success",
            "summary": {
                "pending_reconciliation_tasks": pending_count or 0,
                "completed_tasks_30d": completed_count or 0,
                "date_updates_7d": recent_updates,
                "last_sync": last_sync.isoformat() if last_sync else None,
            }
        }

    except Exception as e:
        logger.error(f"Error getting date reconciliation summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
