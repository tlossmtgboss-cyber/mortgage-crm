"""
Document Email Import Routes
Import document upload notification emails and create review tasks
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging
import json
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Activity': main.Activity,
        'ActivityType': main.ActivityType,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user_flexible


class DocumentEmailImportRequest(BaseModel):
    """Request model for importing document upload notification emails"""
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    from_email: str
    from_name: str
    subject: str
    body: str
    received_date: Optional[str] = None
    has_attachments: bool = True
    attachment_names: Optional[List[str]] = None
    create_task: bool = True


@router.post("/email/import-document-notification")
async def import_document_notification_email(
    request: DocumentEmailImportRequest,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_flexible_dep)
):
    """
    Import a document upload notification email and optionally create a review task.

    This endpoint:
    1. Creates an activity record for the email (displayed in profile email history)
    2. Creates a conversation log entry (for email intelligence tracking)
    3. Optionally creates a task to review the uploaded documents
    """
    models = get_models()
    Activity = models['Activity']
    ActivityType = models['ActivityType']

    try:
        if not current_user or not getattr(current_user, 'id', None):
            raise HTTPException(status_code=401, detail="Could not determine user identity")
        user_id = current_user.id
        now = datetime.now(timezone.utc)

        # Parse received_date if provided
        received_at = now
        if request.received_date:
            try:
                received_at = datetime.fromisoformat(request.received_date.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                received_at = now

        results = {
            "success": True,
            "activity_created": False,
            "conversation_log_created": False,
            "task_created": False,
            "activity_id": None,
            "task_id": None,
            "lead_id": request.lead_id,
            "loan_id": request.loan_id
        }

        # 1. Create Activity record
        activity_content = f"From: {request.from_name} <{request.from_email}>\nSubject: {request.subject}\n\n{request.body}"
        if request.attachment_names:
            activity_content += f"\n\nAttachments: {', '.join(request.attachment_names)}"

        try:
            new_activity = Activity(
                lead_id=request.lead_id,
                loan_id=request.loan_id,
                type=ActivityType.EMAIL,
                content=activity_content,
                created_at=received_at,
                user_id=user_id
            )
            db.add(new_activity)
            db.commit()
            db.refresh(new_activity)
            results["activity_created"] = True
            results["activity_id"] = new_activity.id
            logger.info(f"Created activity {new_activity.id} for document email")
        except Exception as e:
            logger.error(f"Failed to create activity: {e}")
            results["activity_error"] = str(e)
            try:
                db.rollback()
            except Exception as e:
                logger.error(f"Error during rollback in process_document_email: {e}")

        # 2. Create conversation log entry for email intelligence
        try:
            table_check = db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'email_conversation_log'
                )
            """)).scalar()

            if table_check:
                conv_result = db.execute(text("""
                    INSERT INTO email_conversation_log (
                        lead_id, loan_id, email_subject, email_date, direction,
                        summary, documents_received, sentiment, urgency_level,
                        user_id, created_at
                    ) VALUES (
                        :lead_id, :loan_id, :subject, :email_date, 'inbound',
                        :summary, :docs_received, 'neutral', 3,
                        :user_id, :created_at
                    ) RETURNING id
                """), {
                    "lead_id": request.lead_id,
                    "loan_id": request.loan_id,
                    "subject": request.subject,
                    "email_date": received_at,
                    "summary": f"Document upload notification from {request.from_name}: {request.subject}",
                    "docs_received": json.dumps(request.attachment_names or []),
                    "user_id": user_id,
                    "created_at": now
                })
                conv_log_id = conv_result.fetchone()[0]
                results["conversation_log_created"] = True
                results["conversation_log_id"] = conv_log_id
                db.commit()
        except Exception as e:
            logger.warning(f"Could not create conversation log: {e}")
            db.rollback()

        # 3. Create task to review documents if requested
        if request.create_task:
            try:
                task_title = f"Review documents from {request.from_name}"
                if request.attachment_names:
                    task_title = f"Review {len(request.attachment_names)} document(s) from {request.from_name}"

                task_description = f"Documents uploaded via email\n\nFrom: {request.from_name} <{request.from_email}>\nSubject: {request.subject}"
                if request.attachment_names:
                    task_description += f"\n\nDocuments to review:\n" + "\n".join([f"• {name}" for name in request.attachment_names])
                task_description += f"\n\nOriginal email:\n{request.body[:500]}..."

                due_date = now + timedelta(days=1)

                task_result = db.execute(text("""
                    INSERT INTO tasks (
                        title, description, due_date, priority,
                        lead_id, loan_id, owner_id, status,
                        related_contact_name, related_type, created_at
                    ) VALUES (
                        :title, :description, :due_date, 'high',
                        :lead_id, :loan_id, :owner_id, 'pending',
                        :contact_name, 'document_review', :created_at
                    ) RETURNING id
                """), {
                    "title": task_title[:255],
                    "description": task_description,
                    "due_date": due_date,
                    "lead_id": request.lead_id,
                    "loan_id": request.loan_id,
                    "owner_id": user_id,
                    "contact_name": request.from_name,
                    "created_at": now
                })
                task_id = task_result.fetchone()[0]
                results["task_created"] = True
                results["task_id"] = task_id
                db.commit()
                logger.info(f"Created task {task_id} to review documents from {request.from_name}")
            except Exception as e:
                logger.error(f"Failed to create task: {e}")
                db.rollback()

        return results

    except Exception as e:
        logger.error(f"Error importing document notification email: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
