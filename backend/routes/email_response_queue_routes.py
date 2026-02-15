"""
Email Response Queue Routes - AI Training for Email Handling

This module handles the email response queue system which provides AI-assisted
email handling with human-in-the-loop approval. Key features:

- Pending email responses awaiting user review
- Approval/rejection workflow that trains the AI
- Pattern learning from user feedback
- Statistics and analytics for email handling performance

The system learns from user approvals/rejections to improve recommendations
and can eventually auto-execute responses for high-confidence patterns.
"""

import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from utils.pii_mask import mask_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["email-response-queue"])


# =============================================================================
# Dependency Injection Setup
# =============================================================================

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")

    # Try Authorization header first
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    # Fall back to query param (for browser redirects like OAuth flows)
    if not token:
        token = request.query_params.get("token", "")

    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class EmailResponseApproval(BaseModel):
    """Schema for approving/rejecting email response recommendations"""
    queue_id: int
    action: str  # 'approve', 'reject', 'modify'
    modified_response: Optional[str] = None
    modified_action: Optional[str] = None  # 'reply', 'create_task', 'archive', 'forward', 'ignore'
    enable_auto_execute: bool = False  # Enable auto-execution for this pattern

    class Config:
        extra = "allow"


# =============================================================================
# Helper Functions
# =============================================================================

async def execute_email_response_action(
    queue_item: Any,
    final_action: str,
    final_response: str,
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    Execute the approved email response action.

    Actions supported:
    - acknowledge_and_update: Send reply email and update matched entity status
    - reply: Just send reply email
    - create_task: Create a task for follow-up
    - archive: Mark as handled without action
    - ignore: Do nothing

    Returns dict with execution results.
    """
    # Runtime import to avoid circular imports
    from email_service import EmailService

    results = {
        "email_sent": False,
        "status_updated": False,
        "task_created": False,
        "errors": []
    }

    try:
        # Actions that require sending an email reply
        if final_action in ["acknowledge_and_update", "reply", "send_reply"]:
            if final_response and queue_item.sender_email:
                try:
                    from email_service import email_service

                    # Build reply subject
                    original_subject = queue_item.subject or "Your Email"
                    reply_subject = f"Re: {original_subject}" if not original_subject.startswith("Re:") else original_subject

                    # Build HTML response
                    html_body = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px;">
                        <p>{final_response.replace(chr(10), '<br>')}</p>
                        <br>
                        <p style="color: #666; font-size: 12px;">
                            This response was sent on behalf of your loan officer.
                        </p>
                    </div>
                    """

                    # Send the reply (routes through Salesforce when connected)
                    email_sent = await email_service.send_html_email_sf(
                        to_email=queue_item.sender_email,
                        subject=reply_subject,
                        html_body=html_body,
                        plain_text_body=final_response,
                        db=db,
                        user_id=user_id,
                    )

                    results["email_sent"] = email_sent
                    if email_sent:
                        logger.info(f"Sent email reply to {mask_email(queue_item.sender_email)} for queue item {queue_item.id}")
                    else:
                        results["errors"].append("Email service returned failure")

                except Exception as e:
                    logger.error(f"Failed to send email reply: {e}")
                    results["errors"].append(f"Email send failed: {str(e)}")

        # Actions that require updating entity status
        if final_action in ["acknowledge_and_update", "update_status"]:
            if queue_item.matched_entity_type and queue_item.matched_entity_id:
                try:
                    entity_type = queue_item.matched_entity_type
                    entity_id = queue_item.matched_entity_id
                    email_intent = queue_item.email_intent

                    # Map email intent to status update
                    status_mapping = {
                        "Clear to Close": "Clear to Close",
                        "Underwriting Update": "In Underwriting",
                        "Conditional Approval": "Conditionally Approved",
                        "Final Approval": "Approved",
                        "Funded": "Funded",
                        "Closing Scheduled": "Closing Scheduled",
                        "Docs Out": "Docs Out",
                        "Docs Back": "Docs Back"
                    }

                    new_status = status_mapping.get(email_intent)

                    if new_status and entity_type.lower() == "loan":
                        # Update loan status
                        db.execute(text("""
                            UPDATE loans
                            SET status = :status,
                                updated_at = NOW()
                            WHERE id = :loan_id
                        """), {"status": new_status, "loan_id": entity_id})

                        # Log the status change
                        db.execute(text("""
                            INSERT INTO loan_status_history
                            (loan_id, old_status, new_status, changed_by, change_reason, created_at)
                            SELECT :loan_id, status, :new_status, :user_id, :reason, NOW()
                            FROM loans WHERE id = :loan_id
                        """), {
                            "loan_id": entity_id,
                            "new_status": new_status,
                            "user_id": user_id,
                            "reason": f"Auto-updated from email: {queue_item.subject}"
                        })

                        results["status_updated"] = True
                        logger.info(f"Updated loan {entity_id} status to {new_status}")

                except Exception as e:
                    logger.error(f"Failed to update entity status: {e}")
                    results["errors"].append(f"Status update failed: {str(e)}")

        # Actions that create a task
        if final_action == "create_task":
            try:
                task_title = f"Follow up: {queue_item.subject}"
                task_description = f"Email from {queue_item.sender_email}\n\nRecommended action: {final_response}"

                db.execute(text("""
                    INSERT INTO tasks
                    (title, description, assigned_to, status, priority, created_at, due_date)
                    VALUES (:title, :description, :user_id, 'pending', 'normal', NOW(), NOW() + INTERVAL '1 day')
                """), {
                    "title": task_title,
                    "description": task_description,
                    "user_id": user_id
                })

                results["task_created"] = True
                logger.info(f"Created follow-up task for queue item {queue_item.id}")

            except Exception as e:
                logger.error(f"Failed to create task: {e}")
                results["errors"].append(f"Task creation failed: {str(e)}")

        # Log the execution timestamp
        db.execute(text("""
            UPDATE email_response_queue
            SET executed_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": queue_item.id})

    except Exception as e:
        logger.error(f"Error executing email response action: {e}")
        results["errors"].append(str(e))

    return results


# =============================================================================
# Route Handlers
# =============================================================================

@router.get("/email-response-queue/pending")
async def get_pending_email_responses(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all pending email responses awaiting user review"""
    try:
        result = db.execute(text("""
            SELECT
                erq.id, erq.email_id, erq.sender_email, erq.sender_name,
                erq.subject, erq.body_preview, erq.received_at,
                erq.email_intent, erq.intent_confidence,
                erq.matched_entity_type, erq.matched_entity_id, erq.matched_entity_name,
                erq.recommended_action, erq.recommended_response,
                erq.recommendation_reasoning, erq.recommendation_confidence,
                erq.matched_pattern_id, erq.pattern_confidence,
                erq.status, erq.priority, erq.created_at, erq.expires_at
            FROM email_response_queue erq
            WHERE erq.user_id = :user_id
              AND erq.status = 'pending'
            ORDER BY
                CASE erq.priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    ELSE 4
                END,
                erq.created_at DESC
        """), {"user_id": current_user.id})

        pending = result.fetchall()

        items = []
        for row in pending:
            items.append({
                "id": row.id,
                "email_id": row.email_id,
                "sender": {
                    "email": row.sender_email,
                    "name": row.sender_name,
                },
                "subject": row.subject,
                "body_preview": row.body_preview,
                "received_at": row.received_at.isoformat() if row.received_at else None,
                "email_intent": row.email_intent,
                "intent_confidence": float(row.intent_confidence) if row.intent_confidence else None,
                "matched_entity": {
                    "type": row.matched_entity_type,
                    "id": row.matched_entity_id,
                    "name": row.matched_entity_name,
                } if row.matched_entity_type else None,
                "recommendation": {
                    "action": row.recommended_action,
                    "response": row.recommended_response,
                    "reasoning": row.recommendation_reasoning,
                    "confidence": float(row.recommendation_confidence) if row.recommendation_confidence else None,
                },
                "matched_pattern_id": row.matched_pattern_id,
                "pattern_confidence": float(row.pattern_confidence) if row.pattern_confidence else None,
                "priority": row.priority,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            })

        return {
            "status": "success",
            "count": len(items),
            "items": items
        }
    except Exception as e:
        logger.error(f"Error getting pending email responses: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email-response-queue/approve")
async def approve_email_response(
    approval: EmailResponseApproval,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Approve an email response recommendation.

    This creates/updates patterns in email_response_patterns table.
    When the same sender/intent is seen again, the AI will have higher confidence
    to handle it automatically.
    """
    try:
        # Get the queue item
        result = db.execute(text("""
            SELECT erq.*, ide.sender as event_sender
            FROM email_response_queue erq
            LEFT JOIN incoming_data_events ide ON ide.external_message_id = erq.email_id
            WHERE erq.id = :queue_id AND erq.user_id = :user_id
        """), {"queue_id": approval.queue_id, "user_id": current_user.id})

        queue_item = result.fetchone()
        if not queue_item:
            raise HTTPException(status_code=404, detail="Queue item not found")

        if queue_item.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Item already processed: {queue_item.status}")

        # Determine final action and response
        final_action = approval.modified_action or queue_item.recommended_action
        final_response = approval.modified_response or queue_item.recommended_response

        # Update or create response pattern
        sender_domain = queue_item.sender_email.split("@")[1] if "@" in queue_item.sender_email else ""

        # Check if pattern exists
        pattern_result = db.execute(text("""
            SELECT id, approval_count, rejection_count FROM email_response_patterns
            WHERE user_id = :user_id
              AND pattern_type = 'sender_domain'
              AND pattern_value = :domain
              AND response_type = :response_type
        """), {
            "user_id": current_user.id,
            "domain": sender_domain,
            "response_type": final_action
        })
        existing_pattern = pattern_result.fetchone()

        if existing_pattern:
            # Increment approval count
            db.execute(text("""
                UPDATE email_response_patterns
                SET approval_count = approval_count + 1,
                    last_approved_at = NOW(),
                    last_matched_at = NOW(),
                    is_active = CASE WHEN :enable_auto THEN true ELSE is_active END
                WHERE id = :pattern_id
            """), {
                "pattern_id": existing_pattern.id,
                "enable_auto": approval.enable_auto_execute
            })
            pattern_id = existing_pattern.id
        else:
            # Create new pattern
            new_pattern = db.execute(text("""
                INSERT INTO email_response_patterns
                (user_id, pattern_type, pattern_value, response_type, approval_count,
                 is_active, last_approved_at, created_at)
                VALUES (:user_id, 'sender_domain', :domain, :response_type, 1,
                        :is_active, NOW(), NOW())
                RETURNING id
            """), {
                "user_id": current_user.id,
                "domain": sender_domain,
                "response_type": final_action,
                "is_active": approval.enable_auto_execute
            })
            pattern_id = new_pattern.fetchone().id

        # Log the approval
        db.execute(text("""
            INSERT INTO email_response_log
            (user_id, email_id, sender_email, sender_domain, subject, email_intent,
             response_type, response_pattern_id, was_auto_executed,
             ai_recommended_action, ai_confidence, user_action, created_at)
            VALUES (:user_id, :email_id, :sender_email, :sender_domain, :subject, :intent,
                    :response_type, :pattern_id, false,
                    :ai_action, :ai_confidence, 'approved', NOW())
        """), {
            "user_id": current_user.id,
            "email_id": queue_item.email_id,
            "sender_email": queue_item.sender_email,
            "sender_domain": sender_domain,
            "subject": queue_item.subject,
            "intent": queue_item.email_intent,
            "response_type": final_action,
            "pattern_id": pattern_id,
            "ai_action": queue_item.recommended_action,
            "ai_confidence": queue_item.recommendation_confidence
        })

        # Update queue item status
        db.execute(text("""
            UPDATE email_response_queue
            SET status = 'approved',
                reviewed_by = :user_id,
                reviewed_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": approval.queue_id, "user_id": current_user.id})

        db.commit()

        # Execute the approved action (send email, update status, create task, etc.)
        execution_result = await execute_email_response_action(
            queue_item=queue_item,
            final_action=final_action,
            final_response=final_response,
            user_id=current_user.id,
            db=db
        )
        db.commit()  # Commit execution changes

        return {
            "status": "success",
            "message": f"Email response approved and executed.",
            "pattern_id": pattern_id,
            "action_taken": final_action,
            "auto_execute_enabled": approval.enable_auto_execute,
            "execution_result": execution_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving email response: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email-response-queue/reject")
async def reject_email_response(
    rejection: EmailResponseApproval,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reject an email response recommendation.

    This reduces confidence in the pattern, teaching the AI not to auto-execute
    similar emails in the future.
    """
    try:
        # Get the queue item
        result = db.execute(text("""
            SELECT * FROM email_response_queue
            WHERE id = :queue_id AND user_id = :user_id
        """), {"queue_id": rejection.queue_id, "user_id": current_user.id})

        queue_item = result.fetchone()
        if not queue_item:
            raise HTTPException(status_code=404, detail="Queue item not found")

        if queue_item.status != 'pending':
            raise HTTPException(status_code=400, detail=f"Item already processed: {queue_item.status}")

        sender_domain = queue_item.sender_email.split("@")[1] if "@" in queue_item.sender_email else ""

        # If there's a matching pattern, increment rejection count
        if queue_item.matched_pattern_id:
            db.execute(text("""
                UPDATE email_response_patterns
                SET rejection_count = rejection_count + 1,
                    is_active = false  -- Disable auto-execution on rejection
                WHERE id = :pattern_id
            """), {"pattern_id": queue_item.matched_pattern_id})

        # Log the rejection
        db.execute(text("""
            INSERT INTO email_response_log
            (user_id, email_id, sender_email, sender_domain, subject, email_intent,
             response_type, response_pattern_id, was_auto_executed,
             ai_recommended_action, ai_confidence, user_action, created_at)
            VALUES (:user_id, :email_id, :sender_email, :sender_domain, :subject, :intent,
                    :response_type, :pattern_id, false,
                    :ai_action, :ai_confidence, 'rejected', NOW())
        """), {
            "user_id": current_user.id,
            "email_id": queue_item.email_id,
            "sender_email": queue_item.sender_email,
            "sender_domain": sender_domain,
            "subject": queue_item.subject,
            "intent": queue_item.email_intent,
            "response_type": queue_item.recommended_action,
            "pattern_id": queue_item.matched_pattern_id,
            "ai_action": queue_item.recommended_action,
            "ai_confidence": queue_item.recommendation_confidence
        })

        # Update queue item status
        db.execute(text("""
            UPDATE email_response_queue
            SET status = 'rejected',
                reviewed_by = :user_id,
                reviewed_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": rejection.queue_id, "user_id": current_user.id})

        db.commit()

        return {
            "status": "success",
            "message": "Email response rejected. AI will learn from this feedback.",
            "pattern_updated": queue_item.matched_pattern_id is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting email response: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/email-response-patterns")
async def get_email_response_patterns(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all learned email response patterns for the user"""
    try:
        result = db.execute(text("""
            SELECT
                id, pattern_type, pattern_value, response_type,
                approval_count, rejection_count, confidence_score,
                is_active, auto_execute_threshold, requires_entity_match,
                last_matched_at, last_approved_at, created_at
            FROM email_response_patterns
            WHERE user_id = :user_id
            ORDER BY confidence_score DESC, approval_count DESC
        """), {"user_id": current_user.id})

        patterns = result.fetchall()

        items = []
        for row in patterns:
            # Calculate approval rate
            total = (row.approval_count or 0) + (row.rejection_count or 0)
            approval_rate = ((row.approval_count or 0) / total * 100) if total > 0 else 0

            items.append({
                "id": row.id,
                "pattern_type": row.pattern_type,
                "pattern_value": row.pattern_value,
                "response_type": row.response_type,
                "stats": {
                    "approvals": row.approval_count or 0,
                    "rejections": row.rejection_count or 0,
                    "approval_rate": round(approval_rate, 1),
                    "confidence_score": float(row.confidence_score) if row.confidence_score else 0.5,
                },
                "auto_execute": {
                    "enabled": row.is_active,
                    "threshold": float(row.auto_execute_threshold) if row.auto_execute_threshold else 0.95,
                    "requires_entity_match": row.requires_entity_match,
                },
                "last_matched_at": row.last_matched_at.isoformat() if row.last_matched_at else None,
                "last_approved_at": row.last_approved_at.isoformat() if row.last_approved_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

        return {
            "status": "success",
            "count": len(items),
            "patterns": items
        }
    except Exception as e:
        logger.error(f"Error getting email response patterns: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/email-response-patterns/{pattern_id}")
async def update_email_response_pattern(
    pattern_id: int,
    is_active: Optional[bool] = None,
    auto_execute_threshold: Optional[float] = None,
    requires_entity_match: Optional[bool] = None,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update settings for a learned email response pattern"""
    try:
        # Verify ownership
        result = db.execute(text("""
            SELECT id FROM email_response_patterns
            WHERE id = :pattern_id AND user_id = :user_id
        """), {"pattern_id": pattern_id, "user_id": current_user.id})

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Pattern not found")

        # Build update query
        updates = []
        params = {"pattern_id": pattern_id}

        if is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = is_active
        if auto_execute_threshold is not None:
            updates.append("auto_execute_threshold = :threshold")
            params["threshold"] = auto_execute_threshold
        if requires_entity_match is not None:
            updates.append("requires_entity_match = :requires_match")
            params["requires_match"] = requires_entity_match

        if updates:
            updates.append("updated_at = NOW()")
            db.execute(text(f"""
                UPDATE email_response_patterns
                SET {", ".join(updates)}
                WHERE id = :pattern_id
            """), params)
            db.commit()

        return {
            "status": "success",
            "message": "Pattern updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating email response pattern: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/email-response-patterns/{pattern_id}")
async def delete_email_response_pattern(
    pattern_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a learned email response pattern"""
    try:
        result = db.execute(text("""
            DELETE FROM email_response_patterns
            WHERE id = :pattern_id AND user_id = :user_id
            RETURNING id
        """), {"pattern_id": pattern_id, "user_id": current_user.id})

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Pattern not found")

        db.commit()

        return {
            "status": "success",
            "message": "Pattern deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting email response pattern: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/email-response-queue/stats")
async def get_email_response_stats(
    days: int = 30,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get statistics about email response handling"""
    try:
        result = db.execute(text("""
            SELECT
                COUNT(*) as total_emails,
                COUNT(CASE WHEN user_action = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN user_action = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN was_auto_executed THEN 1 END) as auto_executed,
                AVG(ai_confidence) as avg_ai_confidence
            FROM email_response_log
            WHERE user_id = :user_id
              AND created_at >= CURRENT_DATE - :days
        """), {"user_id": current_user.id, "days": days})

        stats = result.fetchone()

        # Get pattern stats
        patterns_result = db.execute(text("""
            SELECT
                COUNT(*) as total_patterns,
                COUNT(CASE WHEN is_active THEN 1 END) as active_patterns,
                AVG(confidence_score) as avg_confidence
            FROM email_response_patterns
            WHERE user_id = :user_id
        """), {"user_id": current_user.id})

        pattern_stats = patterns_result.fetchone()

        # Get pending count
        pending_result = db.execute(text("""
            SELECT COUNT(*) as pending_count
            FROM email_response_queue
            WHERE user_id = :user_id AND status = 'pending'
        """), {"user_id": current_user.id})

        pending = pending_result.fetchone()

        return {
            "status": "success",
            "period_days": days,
            "email_handling": {
                "total_processed": stats.total_emails or 0,
                "approved": stats.approved or 0,
                "rejected": stats.rejected or 0,
                "auto_executed": stats.auto_executed or 0,
                "avg_ai_confidence": float(stats.avg_ai_confidence) if stats.avg_ai_confidence else 0,
                "approval_rate": round((stats.approved / stats.total_emails * 100) if stats.total_emails else 0, 1),
            },
            "patterns": {
                "total": pattern_stats.total_patterns or 0,
                "active": pattern_stats.active_patterns or 0,
                "avg_confidence": float(pattern_stats.avg_confidence) if pattern_stats.avg_confidence else 0,
            },
            "pending_count": pending.pending_count or 0
        }
    except Exception as e:
        logger.error(f"Error getting email response stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email-response-queue/test-item")
async def create_test_email_response_item(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a test email response queue item for testing the approval flow.
    This simulates an incoming email that needs user review.
    """
    try:
        import uuid
        test_email_id = f"test-{uuid.uuid4().hex[:8]}"

        db.execute(text("""
            INSERT INTO email_response_queue
            (user_id, email_id, sender_email, sender_name, subject, body_preview,
             received_at, email_intent, intent_confidence,
             recommended_action, recommended_response, recommendation_reasoning,
             recommendation_confidence, status, priority, created_at)
            VALUES
            (:user_id, :email_id, :sender_email, :sender_name, :subject, :body_preview,
             NOW(), :email_intent, :intent_confidence,
             :recommended_action, :recommended_response, :recommendation_reasoning,
             :recommendation_confidence, 'pending', 'normal', NOW())
        """), {
            "user_id": current_user.id,
            "email_id": test_email_id,
            "sender_email": "titlecompany@test.com",
            "sender_name": "Test Title Company",
            "subject": "Clear to Close - Smith Loan #12345",
            "body_preview": "We are pleased to inform you that the Smith loan is now clear to close. Please schedule the closing at your earliest convenience.",
            "email_intent": "Clear to Close",
            "intent_confidence": 0.95,
            "recommended_action": "acknowledge_and_update",
            "recommended_response": "Thank you for the CTC notification. I will update the loan status and schedule closing.",
            "recommendation_reasoning": "Email indicates Clear to Close status. Recommend acknowledging and updating loan status.",
            "recommendation_confidence": 0.88,
        })
        db.commit()

        return {
            "status": "success",
            "message": "Test email response queue item created",
            "email_id": test_email_id,
            "test_data": {
                "sender": "titlecompany@test.com",
                "subject": "Clear to Close - Smith Loan #12345",
                "recommended_action": "acknowledge_and_update"
            }
        }
    except Exception as e:
        logger.error(f"Error creating test item: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
