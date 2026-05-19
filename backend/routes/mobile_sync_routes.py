"""
Mobile Offline Sync Routes

POST /api/v1/mobile/sync/batch — Process a batch of queued mutations from
mobile clients that were offline. Each operation is processed sequentially
with last-write-wins conflict resolution based on client timestamps.

Supported operation types:
  - create_task
  - update_lead
  - update_loan
  - log_call
  - add_note
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep
from middleware.mobile_error_handler import (
    MobileErrorCode,
    mobile_error,
    mobile_error_response,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/mobile/sync",
    tags=["Mobile Sync"],
    dependencies=[Depends(require_auth)],
)

# ============================================================================
# Request / Response schemas
# ============================================================================

SUPPORTED_OPERATIONS = {"create_task", "update_lead", "update_loan", "log_call", "add_note"}

# Maximum operations per batch (prevent abuse)
MAX_BATCH_SIZE = 100


class SyncOperation(BaseModel):
    """A single queued mutation from the mobile client."""
    type: str = Field(..., description="Operation type (create_task, update_lead, etc.)")
    data: Dict[str, Any] = Field(..., description="Operation payload")
    client_id: str = Field(..., description="Client-generated UUID for idempotency")
    timestamp: str = Field(..., description="ISO 8601 timestamp when the operation was created on device")


class SyncBatchRequest(BaseModel):
    """Batch of offline mutations to process."""
    operations: List[SyncOperation] = Field(..., min_length=1)


class OperationResult(BaseModel):
    """Result of a single operation."""
    client_id: str
    success: bool
    server_id: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class SyncBatchResponse(BaseModel):
    """Response containing per-operation results."""
    processed: int
    succeeded: int
    failed: int
    results: List[OperationResult]


# ============================================================================
# Helpers
# ============================================================================

def _parse_client_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


# Allowlists of columns that mobile clients may set/update for each entity.
# Keeps the sync surface small and prevents mutation of internal fields
# (organization_id, owner_id, etc. are set server-side).

_TASK_CREATE_FIELDS = {
    "title", "description", "status", "priority", "due_date",
    "lead_id", "loan_id", "related_contact_name", "related_type",
}

_LEAD_UPDATE_FIELDS = {
    "stage", "name", "first_name", "last_name", "email", "phone",
    "source", "notes", "next_action", "ai_score", "sentiment",
    "preferred_communication", "loan_type",
}

_LOAN_UPDATE_FIELDS = {
    "stage", "borrower_name", "program", "loan_type", "processor",
    "underwriter", "notes",
}

_CALL_LOG_FIELDS = {
    "contact_phone", "contact_name", "lead_id", "loan_id",
    "notes", "disposition", "duration_seconds", "outcome",
}

_NOTE_FIELDS = {
    "content", "lead_id", "loan_id",
}


def _apply_allowed_fields(data: dict, allowed: set) -> dict:
    """Filter data dict to only allowed keys and drop None values."""
    return {k: v for k, v in data.items() if k in allowed and v is not None}


# ============================================================================
# Operation processors
# ============================================================================

def _process_create_task(
    data: dict,
    client_ts: Optional[datetime],
    user,
    db: Session,
) -> OperationResult:
    from database.models.task import Task

    fields = _apply_allowed_fields(data, _TASK_CREATE_FIELDS)
    if not fields.get("title"):
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.VALIDATION_ERROR.value,
            error_message="Task title is required",
        )

    # Parse due_date if provided as string
    if "due_date" in fields and isinstance(fields["due_date"], str):
        parsed = _parse_client_timestamp(fields["due_date"])
        if parsed:
            fields["due_date"] = parsed
        else:
            del fields["due_date"]

    task = Task(
        organization_id=user.organization_id,
        owner_id=user.id,
        **fields,
    )
    if client_ts:
        task.created_at = client_ts

    db.add(task)
    db.flush()  # Get the server-assigned ID
    return OperationResult(client_id="", success=True, server_id=task.id)


def _process_update_lead(
    data: dict,
    client_ts: Optional[datetime],
    user,
    db: Session,
) -> OperationResult:
    from database.models.lead_loan import Lead

    lead_id = data.get("id")
    if not lead_id:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.VALIDATION_ERROR.value,
            error_message="Lead id is required",
        )

    lead = db.query(Lead).filter(
        Lead.id == int(lead_id),
        Lead.organization_id == user.organization_id,
    ).first()

    if not lead:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.ENTITY_NOT_FOUND.value,
            error_message=f"Lead {lead_id} not found",
        )

    # Last-write-wins: skip if server copy is newer than client timestamp
    if client_ts and lead.updated_at and lead.updated_at > client_ts:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.SYNC_CONFLICT.value,
            error_message="Server version is newer than client version",
        )

    fields = _apply_allowed_fields(data, _LEAD_UPDATE_FIELDS)
    for key, value in fields.items():
        setattr(lead, key, value)
    lead.updated_at = datetime.now(timezone.utc)

    db.flush()
    return OperationResult(client_id="", success=True, server_id=lead.id)


def _process_update_loan(
    data: dict,
    client_ts: Optional[datetime],
    user,
    db: Session,
) -> OperationResult:
    from database.models.lead_loan import Loan

    loan_id = data.get("id")
    if not loan_id:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.VALIDATION_ERROR.value,
            error_message="Loan id is required",
        )

    loan = db.query(Loan).filter(
        Loan.id == int(loan_id),
        Loan.organization_id == user.organization_id,
    ).first()

    if not loan:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.ENTITY_NOT_FOUND.value,
            error_message=f"Loan {loan_id} not found",
        )

    # Last-write-wins conflict resolution
    if client_ts and loan.updated_at and loan.updated_at > client_ts:
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.SYNC_CONFLICT.value,
            error_message="Server version is newer than client version",
        )

    fields = _apply_allowed_fields(data, _LOAN_UPDATE_FIELDS)
    for key, value in fields.items():
        setattr(loan, key, value)
    loan.updated_at = datetime.now(timezone.utc)

    db.flush()
    return OperationResult(client_id="", success=True, server_id=loan.id)


def _process_log_call(
    data: dict,
    client_ts: Optional[datetime],
    user,
    db: Session,
) -> OperationResult:
    from database.models.dialer import CallLog

    fields = _apply_allowed_fields(data, _CALL_LOG_FIELDS)
    if not fields.get("contact_phone") and not fields.get("contact_name"):
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.VALIDATION_ERROR.value,
            error_message="contact_phone or contact_name is required",
        )

    # Default contact_phone to empty string if only name provided
    if not fields.get("contact_phone"):
        fields["contact_phone"] = ""

    call_log = CallLog(
        organization_id=user.organization_id,
        agent_id=user.id,
        **fields,
    )
    if client_ts:
        call_log.created_at = client_ts

    db.add(call_log)
    db.flush()
    return OperationResult(client_id="", success=True, server_id=call_log.id)


def _process_add_note(
    data: dict,
    client_ts: Optional[datetime],
    user,
    db: Session,
) -> OperationResult:
    from database.models.communication import Activity
    from database.enums import ActivityType

    fields = _apply_allowed_fields(data, _NOTE_FIELDS)
    if not fields.get("content"):
        return OperationResult(
            client_id="",
            success=False,
            error_code=MobileErrorCode.VALIDATION_ERROR.value,
            error_message="Note content is required",
        )

    activity = Activity(
        organization_id=user.organization_id,
        user_id=user.id,
        type=ActivityType.NOTE,
        **fields,
    )
    if client_ts:
        activity.created_at = client_ts

    db.add(activity)
    db.flush()
    return OperationResult(client_id="", success=True, server_id=activity.id)


# Dispatch table
_OPERATION_HANDLERS = {
    "create_task": _process_create_task,
    "update_lead": _process_update_lead,
    "update_loan": _process_update_loan,
    "log_call": _process_log_call,
    "add_note": _process_add_note,
}


# ============================================================================
# Route
# ============================================================================

@router.post("/batch", response_model=SyncBatchResponse)
async def sync_batch(
    body: SyncBatchRequest,
    request: Request,
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Process a batch of queued mutations from an offline mobile client.

    Each operation is processed sequentially. For update operations,
    conflict resolution uses last-write-wins based on the client timestamp:
    if the server's updated_at is newer than the client's timestamp, the
    update is rejected with SYNC_CONFLICT.

    Returns per-operation success/failure results with server-assigned IDs.
    """
    if len(body.operations) > MAX_BATCH_SIZE:
        raise mobile_error(
            MobileErrorCode.OFFLINE_QUEUE_FULL,
            f"Batch too large: {len(body.operations)} operations exceeds maximum of {MAX_BATCH_SIZE}",
            details={"max_batch_size": MAX_BATCH_SIZE, "submitted": len(body.operations)},
        )

    results: List[OperationResult] = []
    succeeded = 0
    failed = 0

    for op in body.operations:
        # Validate operation type
        if op.type not in SUPPORTED_OPERATIONS:
            results.append(OperationResult(
                client_id=op.client_id,
                success=False,
                error_code=MobileErrorCode.VALIDATION_ERROR.value,
                error_message=f"Unsupported operation type: {op.type}. Supported: {', '.join(sorted(SUPPORTED_OPERATIONS))}",
            ))
            failed += 1
            continue

        handler = _OPERATION_HANDLERS[op.type]
        client_ts = _parse_client_timestamp(op.timestamp)

        try:
            result = handler(op.data, client_ts, current_user, db)
            result.client_id = op.client_id
            results.append(result)
            if result.success:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            logger.exception(f"Sync operation {op.type} failed for client_id={op.client_id}: {e}")
            await db.rollback()
            results.append(OperationResult(
                client_id=op.client_id,
                success=False,
                error_code=MobileErrorCode.SERVER_ERROR.value,
                error_message="Internal error processing operation",
            ))
            failed += 1

    # Commit all successful operations in one transaction
    try:
        await db.commit()
    except Exception as e:
        logger.exception(f"Sync batch commit failed: {e}")
        await db.rollback()
        # Mark all previously-succeeded operations as failed
        for r in results:
            if r.success:
                r.success = False
                r.server_id = None
                r.error_code = MobileErrorCode.SERVER_ERROR.value
                r.error_message = "Batch commit failed"
                succeeded -= 1
                failed += 1

    logger.info(
        f"Sync batch processed: {len(body.operations)} ops, "
        f"{succeeded} succeeded, {failed} failed, user={current_user.id}"
    )

    return SyncBatchResponse(
        processed=len(body.operations),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )
