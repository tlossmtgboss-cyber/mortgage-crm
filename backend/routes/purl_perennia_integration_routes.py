"""
PURL - Perennia Docs Integration Routes
Perennia AI - Mortgage CRM

Provides integration between PURL workspaces and Perennia Docs AI system.
Enables:
- Unified document management across workspace and loan
- Automatic document request creation from template packs
- Workspace-aware document status tracking
- Combined activity feeds and notifications
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from services.notification_service import NotificationService
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/purl-integration", tags=["PURL Integration"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

from db import get_db

_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies from main.py."""
    global _get_current_user
    _get_current_user = get_current_user_func
    logger.info("PURL Integration routes dependencies set")


async def get_current_user(request, db: Session = Depends(get_db)):
    """Get current user."""
    if _get_current_user is None:
        raise RuntimeError("PURL Integration routes not initialized")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


def send_milestone_notification(db: Session, workspace_id: int, milestone_id: str, status: str):
    """
    Send milestone update notification to borrower.

    Args:
        db: Database session
        workspace_id: The workspace ID
        milestone_id: The milestone identifier
        status: New status (in_progress, completed)
    """
    try:
        # Get borrower contact info and milestone details
        result = db.execute(text("""
            SELECT
                w.borrower_email,
                w.borrower_name,
                w.borrower_phone,
                m.name as milestone_name,
                m.description as milestone_description,
                l.loan_number,
                l.property_address
            FROM purl_workspaces w
            LEFT JOIN purl_loans l ON l.workspace_id = w.id
            LEFT JOIN purl_milestones m ON m.id = :milestone_id
            WHERE w.id = :workspace_id
        """), {"workspace_id": workspace_id, "milestone_id": milestone_id}).fetchone()

        if not result or not result.borrower_email:
            logger.warning(f"Cannot send milestone notification - no borrower email for workspace {workspace_id}")
            return

        notification_service = NotificationService()

        # Determine status message
        if status == "completed":
            status_text = "has been completed"
            emoji = "✅"
        else:  # in_progress
            status_text = "is now in progress"
            emoji = "🔄"

        milestone_name = result.milestone_name or f"Milestone {milestone_id}"

        # Send email notification
        notification_service.send_email(
            to_email=result.borrower_email,
            subject=f"{emoji} Loan Update: {milestone_name} {status_text}",
            html_content=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #1e40af;">Loan Progress Update</h2>
                <p>Hi {result.borrower_name or 'there'},</p>

                <p>Great news! Your loan milestone <strong>{milestone_name}</strong> {status_text}.</p>

                {f'<p><em>{result.milestone_description}</em></p>' if result.milestone_description else ''}

                <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Loan:</strong> {result.loan_number or 'Your Application'}</p>
                    {f'<p style="margin: 5px 0 0 0;"><strong>Property:</strong> {result.property_address}</p>' if result.property_address else ''}
                </div>

                <p>Log in to your portal to see the full status of your loan application.</p>

                <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                    Questions? Reply to this email or contact your loan officer.
                </p>
            </div>
            """
        )

        logger.info(f"Sent milestone notification to {result.borrower_email} for milestone {milestone_id}")

    except Exception as e:
        logger.error(f"Failed to send milestone notification for workspace {workspace_id}: {e}")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class InitializeDocumentsRequest(BaseModel):
    """Request to initialize documents for a workspace."""
    template_pack_id: Optional[int] = None
    loan_type: Optional[str] = None
    employment_type: Optional[str] = None
    property_type: Optional[str] = None


class DocumentRequestSummary(BaseModel):
    """Summary of a document request."""
    id: int
    doc_type: str
    title: str
    status: str
    priority: str
    documents_count: int
    approved_count: int
    is_complete: bool


class WorkspaceDocumentStatus(BaseModel):
    """Complete document status for a workspace."""
    workspace_id: int
    loan_id: Optional[int]
    total_requests: int
    completed_requests: int
    pending_requests: int
    completion_percentage: float
    requests: List[DocumentRequestSummary]


class UnifiedActivityItem(BaseModel):
    """Unified activity item from both systems."""
    id: str
    source: str  # 'purl' or 'perennia_docs'
    event_type: str
    description: str
    actor_type: str
    actor_name: Optional[str]
    created_at: str
    metadata: Optional[Dict[str, Any]] = None


class MilestoneUpdate(BaseModel):
    """Request to update a milestone."""
    milestone_id: int
    status: str
    notes: Optional[str] = None
    auto_notify: bool = True


class WorkspaceNotification(BaseModel):
    """Notification for workspace."""
    id: int
    notification_type: str
    title: str
    message: str
    is_read: bool
    created_at: str
    action_url: Optional[str] = None


# =============================================================================
# DOCUMENT MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/workspaces/{workspace_id}/initialize-documents")
async def initialize_workspace_documents(
    workspace_id: int,
    request: InitializeDocumentsRequest,
    db: Session = Depends(get_db)
):
    """
    Initialize document requirements for a workspace.

    Finds matching template pack and creates document requests.
    Links to both PURL workspace and any associated loan.
    """
    # Get workspace
    workspace = db.execute(text("""
        SELECT w.id, w.organization_id, w.meta_data
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Find matching template pack
    template_query = """
        SELECT id, name, config
        FROM perennia_template_packs
        WHERE is_active = true
    """
    params = {}

    if request.template_pack_id:
        template_query += " AND id = :template_id"
        params["template_id"] = request.template_pack_id
    else:
        # Find by matching criteria
        if request.loan_type:
            template_query += " AND :loan_type = ANY(loan_programs)"
            params["loan_type"] = request.loan_type
        if request.employment_type:
            template_query += " AND :employment_type = ANY(employment_types)"
            params["employment_type"] = request.employment_type

    template_query += " ORDER BY created_at DESC LIMIT 1"

    template = db.execute(text(template_query), params).fetchone()

    if not template:
        raise HTTPException(status_code=404, detail="No matching template pack found")

    template_id = template[0]
    template_name = template[1]
    config = template[2]

    # Get loan_id if available
    loan = db.execute(text("""
        SELECT id FROM purl_loans
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    loan_id = loan[0] if loan else None

    # Also check meta_data for lead_id
    meta_data = workspace[2] or {}
    lead_id = meta_data.get("lead_id")

    # Create document requests from template
    requirements = config.get("documentRequirements", [])
    reminder_schedule = config.get("reminderSchedule", [1, 3, 7])

    created_requests = []

    try:
        for req in requirements:
            result = db.execute(text("""
                INSERT INTO perennia_document_requests (
                    loan_id, lead_id, template_pack_id,
                    doc_type, doc_subtype, title, description,
                    quantity, priority, expiration_threshold,
                    reminder_schedule, status, created_at, updated_at
                ) VALUES (
                    :loan_id, :lead_id, :template_id,
                    :doc_type, :doc_subtype, :title, :description,
                    :quantity, :priority, :expiration_threshold,
                    :reminder_schedule, 'pending', NOW(), NOW()
                ) RETURNING id
            """), {
                "loan_id": loan_id,
                "lead_id": lead_id,
                "template_id": template_id,
                "doc_type": req.get("doc_type"),
                "doc_subtype": req.get("doc_subtype"),
                "title": req.get("title"),
                "description": req.get("description"),
                "quantity": req.get("quantity", 1),
                "priority": "high" if req.get("required", True) else "normal",
                "expiration_threshold": req.get("expiration_threshold", 90),
                "reminder_schedule": reminder_schedule
            })

            request_id = result.fetchone()[0]
            created_requests.append({
                "id": request_id,
                "doc_type": req.get("doc_type"),
                "title": req.get("title")
            })

        # Store template association in workspace meta_data
        db.execute(text("""
            UPDATE purl_workspaces
            SET meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                jsonb_build_object(
                    'template_pack_id', :template_id,
                    'template_name', :template_name,
                    'documents_initialized_at', :now
                ),
                updated_at = NOW()
            WHERE id = :workspace_id
        """), {
            "workspace_id": workspace_id,
            "template_id": template_id,
            "template_name": template_name,
            "now": datetime.now(timezone.utc).isoformat()
        })

        # Log event
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                metadata, created_at
            ) VALUES (
                :org_id, :workspace_id, 'documents_initialized', 'system',
                :metadata, NOW()
            )
        """), {
            "org_id": workspace[1],
            "workspace_id": workspace_id,
            "metadata": {
                "template_id": template_id,
                "template_name": template_name,
                "requests_created": len(created_requests)
            }
        })

        db.commit()

        return {
            "success": True,
            "workspace_id": workspace_id,
            "template_applied": template_name,
            "requests_created": len(created_requests),
            "requests": created_requests
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to initialize documents: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workspaces/{workspace_id}/document-status", response_model=WorkspaceDocumentStatus)
async def get_workspace_document_status(
    workspace_id: int,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive document status for a workspace.

    Returns all document requests with their completion status.
    """
    # Get workspace and associated loan
    workspace = db.execute(text("""
        SELECT w.id, w.meta_data,
               (SELECT id FROM purl_loans WHERE workspace_id = w.id ORDER BY created_at DESC LIMIT 1) as loan_id
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    import json
    loan_id = workspace[2]
    raw_meta = workspace[1] or "{}"
    meta_data = json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
    lead_id = meta_data.get("lead_id") if isinstance(meta_data, dict) else None

    # Build filter for document requests
    if loan_id:
        loan_filter = "loan_id = :loan_id"
        params = {"loan_id": loan_id}
    elif lead_id:
        loan_filter = "lead_id = :lead_id"
        params = {"lead_id": lead_id}
    else:
        return WorkspaceDocumentStatus(
            workspace_id=workspace_id,
            loan_id=None,
            total_requests=0,
            completed_requests=0,
            pending_requests=0,
            completion_percentage=0,
            requests=[]
        )

    # Get document requests with counts
    requests_sql = """
        SELECT
            dr.id, dr.doc_type, dr.title, dr.status, dr.priority, dr.quantity,
            COUNT(d.id) as documents_count,
            COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count
        FROM perennia_document_requests dr
        LEFT JOIN perennia_documents d ON d.request_id = dr.id
        WHERE """ + loan_filter + """ AND dr.status != 'cancelled'
        GROUP BY dr.id
        ORDER BY dr.priority DESC, dr.created_at
    """
    requests = db.execute(text(requests_sql), params).fetchall()

    request_summaries = []
    completed = 0
    pending = 0

    for req in requests:
        is_complete = req[7] >= req[5]  # approved_count >= quantity
        if is_complete:
            completed += 1
        else:
            pending += 1

        request_summaries.append(DocumentRequestSummary(
            id=req[0],
            doc_type=req[1],
            title=req[2],
            status=req[3],
            priority=req[4],
            documents_count=req[6],
            approved_count=req[7],
            is_complete=is_complete
        ))

    total = len(requests)
    completion_pct = (completed / total * 100) if total > 0 else 0

    return WorkspaceDocumentStatus(
        workspace_id=workspace_id,
        loan_id=loan_id,
        total_requests=total,
        completed_requests=completed,
        pending_requests=pending,
        completion_percentage=round(completion_pct, 1),
        requests=request_summaries
    )


@router.get("/workspaces/{workspace_id}/activity-feed")
async def get_unified_activity_feed(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get unified activity feed combining PURL and Perennia Docs events.

    Returns a merged, chronologically sorted list of activities.
    """
    # Get workspace info
    workspace = db.execute(text("""
        SELECT w.id, w.organization_id, w.meta_data
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    meta_data = workspace[2] or {}
    loan_id = None
    lead_id = meta_data.get("lead_id")

    # Get associated loan
    loan = db.execute(text("""
        SELECT id FROM purl_loans WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    if loan:
        loan_id = loan[0]

    activities = []

    # Get PURL audit log events
    purl_events = db.execute(text("""
        SELECT
            'purl_' || id::text as id,
            'purl' as source,
            action as event_type,
            actor_type,
            metadata,
            created_at
        FROM purl_audit_log
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"workspace_id": workspace_id, "limit": limit}).fetchall()

    for event in purl_events:
        activities.append({
            "id": event[0],
            "source": event[1],
            "event_type": event[2],
            "actor_type": event[3],
            "metadata": event[4],
            "created_at": event[5].isoformat() if event[5] else None,
            "description": _format_purl_event(event[2], event[4])
        })

    # Get Perennia Docs events if we have loan_id or lead_id
    if loan_id or lead_id:
        doc_filter = "loan_id = :loan_id" if loan_id else "lead_id = :lead_id"
        params = {"loan_id": loan_id, "lead_id": lead_id, "limit": limit}

        doc_events_sql = """
            SELECT
                'docs_' || id::text as id,
                'perennia_docs' as source,
                event_type,
                actor_type,
                event_data,
                created_at
            FROM perennia_document_events
            WHERE """ + doc_filter + """
            ORDER BY created_at DESC
            LIMIT :limit
        """
        doc_events = db.execute(text(doc_events_sql), params).fetchall()

        for event in doc_events:
            activities.append({
                "id": event[0],
                "source": event[1],
                "event_type": event[2],
                "actor_type": event[3],
                "metadata": event[4],
                "created_at": event[5].isoformat() if event[5] else None,
                "description": _format_docs_event(event[2], event[4])
            })

    # Sort by created_at descending
    activities.sort(key=lambda x: x["created_at"] or "", reverse=True)

    # Apply pagination
    paginated = activities[offset:offset + limit]

    return {
        "activities": paginated,
        "total": len(activities),
        "limit": limit,
        "offset": offset
    }


def _format_purl_event(event_type: str, metadata: Dict) -> str:
    """Format PURL event for display."""
    descriptions = {
        "application_save": "Application progress saved",
        "application_submit": "Application submitted",
        "document_upload": f"Document uploaded: {metadata.get('filename', 'file')}",
        "task_update": "Task updated",
        "message_send": "Message sent",
        "token_create": "Access token created",
        "documents_initialized": "Document checklist created",
        "ai_chat": "AI assistant interaction",
    }
    return descriptions.get(event_type, event_type.replace("_", " ").title())


def _format_docs_event(event_type: str, metadata: Dict) -> str:
    """Format Perennia Docs event for display."""
    descriptions = {
        "request_created": f"Document request created: {metadata.get('title', 'document')}",
        "document_uploaded": "Document uploaded",
        "document_approved": "Document approved",
        "document_rejected": f"Document rejected: {metadata.get('rejection_reason', 'needs review')}",
        "template_applied": f"Template applied: {metadata.get('template_name', 'template')}",
        "reminder_sent": "Document reminder sent",
    }
    return descriptions.get(event_type, event_type.replace("_", " ").title())


# =============================================================================
# MILESTONE MANAGEMENT
# =============================================================================

@router.get("/workspaces/{workspace_id}/milestones")
async def get_workspace_milestones(
    workspace_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get loan milestones for a workspace.

    Returns milestone definitions and current status.
    """
    # Get active loan for workspace
    loan = db.execute(text("""
        SELECT l.id, l.status
        FROM purl_loans l
        WHERE l.workspace_id = :workspace_id
        ORDER BY l.created_at DESC
        LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    if not loan:
        return {
            "workspace_id": workspace_id,
            "loan_id": None,
            "milestones": [],
            "current_milestone": None
        }

    loan_id = loan[0]

    # Get milestones with status
    milestones = db.execute(text("""
        SELECT
            md.id, md.name, md.description, md.order_index,
            md.is_borrower_visible, md.icon_name,
            lm.status, lm.started_at, lm.completed_at, lm.notes
        FROM purl_milestone_definitions md
        LEFT JOIN purl_loan_milestones lm ON lm.milestone_id = md.id AND lm.loan_id = :loan_id
        WHERE md.organization_id = (SELECT organization_id FROM purl_workspaces WHERE id = :workspace_id)
           OR md.organization_id IS NULL
        ORDER BY md.order_index
    """), {"loan_id": loan_id, "workspace_id": workspace_id}).fetchall()

    milestone_list = []
    current_milestone = None

    for m in milestones:
        status = m[6] or "not_started"
        milestone_data = {
            "id": m[0],
            "name": m[1],
            "description": m[2],
            "order": m[3],
            "is_borrower_visible": m[4],
            "icon": m[5],
            "status": status,
            "started_at": m[7].isoformat() if m[7] else None,
            "completed_at": m[8].isoformat() if m[8] else None,
            "notes": m[9]
        }
        milestone_list.append(milestone_data)

        if status == "in_progress" and current_milestone is None:
            current_milestone = milestone_data

    return {
        "workspace_id": workspace_id,
        "loan_id": loan_id,
        "milestones": milestone_list,
        "current_milestone": current_milestone
    }


@router.patch("/workspaces/{workspace_id}/milestones/{milestone_id}")
async def update_workspace_milestone(
    workspace_id: int,
    milestone_id: int,
    update: MilestoneUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Update milestone status for a workspace loan.

    Optionally triggers notifications to borrower.
    """
    # Get loan
    loan = db.execute(text("""
        SELECT l.id, w.organization_id
        FROM purl_loans l
        JOIN purl_workspaces w ON w.id = l.workspace_id
        WHERE l.workspace_id = :workspace_id
        ORDER BY l.created_at DESC
        LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="No loan found for workspace")

    loan_id = loan[0]
    org_id = loan[1]

    try:
        # Check if milestone record exists
        existing = db.execute(text("""
            SELECT id FROM purl_loan_milestones
            WHERE loan_id = :loan_id AND milestone_id = :milestone_id
        """), {"loan_id": loan_id, "milestone_id": milestone_id}).fetchone()

        now = datetime.now(timezone.utc)

        if existing:
            # Update existing
            db.execute(text("""
                UPDATE purl_loan_milestones
                SET status = :status,
                    notes = COALESCE(:notes, notes),
                    started_at = CASE
                        WHEN :status = 'in_progress' AND started_at IS NULL THEN :now
                        ELSE started_at
                    END,
                    completed_at = CASE
                        WHEN :status = 'completed' THEN :now
                        ELSE completed_at
                    END,
                    updated_at = :now
                WHERE loan_id = :loan_id AND milestone_id = :milestone_id
            """), {
                "loan_id": loan_id,
                "milestone_id": milestone_id,
                "status": update.status,
                "notes": update.notes,
                "now": now
            })
        else:
            # Create new milestone record
            db.execute(text("""
                INSERT INTO purl_loan_milestones (
                    organization_id, loan_id, milestone_id,
                    status, notes, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    :org_id, :loan_id, :milestone_id,
                    :status, :notes,
                    CASE WHEN :status IN ('in_progress', 'completed') THEN :now ELSE NULL END,
                    CASE WHEN :status = 'completed' THEN :now ELSE NULL END,
                    :now, :now
                )
            """), {
                "org_id": org_id,
                "loan_id": loan_id,
                "milestone_id": milestone_id,
                "status": update.status,
                "notes": update.notes,
                "now": now
            })

        # Log the update
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                resource_type, resource_id, metadata, created_at
            ) VALUES (
                :org_id, :workspace_id, 'milestone_update', 'system',
                'milestone', :milestone_id,
                :metadata, NOW()
            )
        """), {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "milestone_id": milestone_id,
            "metadata": {"status": update.status, "notes": update.notes}
        })

        db.commit()

        # Send notification to borrower if auto_notify is enabled
        if update.auto_notify and update.status in ["in_progress", "completed"]:
            try:
                send_milestone_notification(db, workspace_id, milestone_id, update.status)
            except Exception as notify_err:
                logger.error(f"Failed to send auto-notification: {notify_err}")
                # Don't fail the update just because notification failed

        return {
            "success": True,
            "milestone_id": milestone_id,
            "status": update.status
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update milestone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# NOTIFICATION MANAGEMENT
# =============================================================================

@router.get("/workspaces/{workspace_id}/notifications")
async def get_workspace_notifications(
    workspace_id: int,
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get notifications for a workspace.

    Combines messages and system notifications.
    """
    # Get unread messages
    unread_filter = "AND m.is_read_by_borrower = false" if unread_only else ""

    messages_sql = """
        SELECT
            m.id,
            'message' as notification_type,
            CASE
                WHEN m.sender_type = 'user' THEN 'Message from your loan team'
                ELSE 'System notification'
            END as title,
            LEFT(m.content, 100) as message,
            m.is_read_by_borrower as is_read,
            m.created_at
        FROM purl_messages m
        WHERE m.workspace_id = :workspace_id
            AND m.sender_type != 'contact'
            """ + unread_filter + """
        ORDER BY m.created_at DESC
        LIMIT :limit
    """
    messages = db.execute(text(messages_sql), {"workspace_id": workspace_id, "limit": limit}).fetchall()

    notifications = []
    for msg in messages:
        notifications.append(WorkspaceNotification(
            id=msg[0],
            notification_type=msg[1],
            title=msg[2],
            message=msg[3] + ("..." if len(msg[3] or "") == 100 else ""),
            is_read=msg[4],
            created_at=msg[5].isoformat() if msg[5] else "",
            action_url=f"/portal/messages/{msg[0]}"
        ))

    # Count unread
    unread_count = db.execute(text("""
        SELECT COUNT(*) FROM purl_messages
        WHERE workspace_id = :workspace_id
            AND sender_type != 'contact'
            AND is_read_by_borrower = false
    """), {"workspace_id": workspace_id}).scalar()

    return {
        "notifications": [n.dict() for n in notifications],
        "unread_count": unread_count,
        "total": len(notifications)
    }


@router.patch("/workspaces/{workspace_id}/notifications/{notification_id}/read")
async def mark_notification_read(
    workspace_id: int,
    notification_id: int,
    db: Session = Depends(get_db)
):
    """Mark a notification as read."""
    result = db.execute(text("""
        UPDATE purl_messages
        SET is_read_by_borrower = true, read_at = NOW()
        WHERE id = :id AND workspace_id = :workspace_id
        RETURNING id
    """), {"id": notification_id, "workspace_id": workspace_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.commit()
    return {"success": True}


@router.patch("/workspaces/{workspace_id}/notifications/mark-all-read")
async def mark_all_notifications_read(
    workspace_id: int,
    db: Session = Depends(get_db)
):
    """Mark all notifications as read."""
    result = db.execute(text("""
        UPDATE purl_messages
        SET is_read_by_borrower = true, read_at = NOW()
        WHERE workspace_id = :workspace_id
            AND sender_type != 'contact'
            AND is_read_by_borrower = false
    """), {"workspace_id": workspace_id})

    db.commit()
    return {"success": True, "count": result.rowcount}


# =============================================================================
# WORKSPACE STATUS SYNC
# =============================================================================

@router.post("/workspaces/{workspace_id}/sync-status")
async def sync_workspace_status(
    workspace_id: int,
    db: Session = Depends(get_db)
):
    """
    Synchronize workspace status based on application, documents, and loan status.

    Automatically updates workspace status based on:
    - Application completeness
    - Document collection progress
    - Loan milestones
    """
    workspace = db.execute(text("""
        SELECT w.id, w.status, w.organization_id
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    current_status = workspace[1]

    # Check application status
    application = db.execute(text("""
        SELECT status, completeness_pct, submitted_at
        FROM purl_applications
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    # Check loan status
    loan = db.execute(text("""
        SELECT id, status
        FROM purl_loans
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC LIMIT 1
    """), {"workspace_id": workspace_id}).fetchone()

    # Determine new status
    new_status = current_status

    if loan:
        loan_status = loan[1]
        if loan_status in ["funded", "closed"]:
            new_status = "mum_homeowner"
        elif loan_status in ["processing", "underwriting", "approved", "clear_to_close"]:
            new_status = "active_loan"
        else:
            new_status = "active_loan"
    elif application:
        if application[2]:  # submitted_at
            new_status = "active_loan"
        elif application[1] and application[1] > 0:  # completeness_pct
            new_status = "application"
        else:
            new_status = "lead"
    else:
        new_status = "lead"

    # Update if changed
    if new_status != current_status:
        db.execute(text("""
            UPDATE purl_workspaces
            SET status = :status, updated_at = NOW()
            WHERE id = :workspace_id
        """), {"workspace_id": workspace_id, "status": new_status})

        # Log the change
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                metadata, created_at
            ) VALUES (
                :org_id, :workspace_id, 'status_sync', 'system',
                :metadata, NOW()
            )
        """), {
            "org_id": workspace[2],
            "workspace_id": workspace_id,
            "metadata": {
                "previous_status": current_status,
                "new_status": new_status
            }
        })

        db.commit()

    return {
        "workspace_id": workspace_id,
        "previous_status": current_status,
        "current_status": new_status,
        "changed": new_status != current_status
    }


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def integration_health():
    """Integration system health check."""
    return {
        "status": "healthy",
        "service": "purl_perennia_integration",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
