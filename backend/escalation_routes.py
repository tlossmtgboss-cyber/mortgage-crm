"""
Escalation Routes
API endpoints for escalating issues to team members
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, TYPE_CHECKING, Any
from datetime import datetime, timezone
import logging
import os
import uuid

from database import get_db

if TYPE_CHECKING:
    from database.models import User, Lead, Task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["escalations"])

# OAuth2 scheme for token extraction (matches main.py)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user_lazy(
    token: str = Depends(oauth2_scheme),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Lazy import wrapper to avoid circular imports"""
    from auth.dependencies import get_current_user
    return await get_current_user(token, request, db)


def get_models():
    """Lazy import models to avoid circular imports"""
    from database.models import User, Lead, Task
    return User, Lead, Task


@router.get("/leads/search")
async def search_leads(
    q: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Search for leads by name or loan number
    Used for borrower autocomplete in escalation panel
    """
    User, Lead, Task = get_models()
    try:
        if not q or len(q) < 2:
            return {"leads": []}

        search_term = f"%{q}%"

        # Search by name or loan number
        query = db.query(Lead).filter(
            or_(
                Lead.name.ilike(search_term),
                Lead.loan_number.ilike(search_term)
            )
        )

        # Order by most recently updated
        query = query.order_by(Lead.updated_at.desc())

        # Apply limit
        leads = query.limit(limit).all()

        # Format results
        results = []
        for lead in leads:
            results.append({
                "id": lead.id,
                "name": lead.name,
                "loan_number": lead.loan_number or str(lead.id),
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage.value if lead.stage else None
            })

        return {"leads": results}

    except Exception as e:
        logger.error(f"Error searching leads: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/escalations")
async def create_escalation(
    assigned_to_id: int = Form(...),
    lead_id: int = Form(...),
    loan_number: str = Form(None),
    borrower_name: str = Form(...),
    message: str = Form(...),
    priority: str = Form("high"),
    attachments: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_lazy)
):
    """
    Create an escalation task assigned to a team member
    """
    User, Lead, Task = get_models()
    try:
        # Verify the assigned user exists
        assigned_user = db.query(User).filter(User.id == assigned_to_id).first()
        if not assigned_user:
            raise HTTPException(status_code=404, detail="Assigned team member not found")

        # Verify the lead exists
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Create task title
        task_title = f"🚨 Escalation: {borrower_name}"

        # Build task description
        task_description = f"""**ESCALATED FROM:** {current_user.full_name or current_user.email}
**BORROWER:** {borrower_name}
**LOAN NUMBER:** {loan_number or 'N/A'}

**ISSUE:**
{message}
"""

        # Handle file attachments
        attachment_paths = []
        if attachments:
            upload_dir = "/tmp/escalation_attachments"
            os.makedirs(upload_dir, exist_ok=True)

            for file in attachments:
                if file.filename:
                    # Generate unique filename — sanitize extension to prevent traversal
                    import re as _re
                    raw_ext = os.path.splitext(file.filename)[1]
                    file_ext = raw_ext if _re.match(r'^\.[a-zA-Z0-9]{1,10}$', raw_ext) else '.bin'
                    BLOCKED_EXTENSIONS = {'.exe', '.com', '.bat', '.cmd', '.sh', '.py', '.js', '.msi', '.scr', '.pif', '.vbs', '.ps1'}
                    if file_ext.lower() in BLOCKED_EXTENSIONS:
                        file_ext = '.bin'
                    unique_filename = f"{uuid.uuid4()}{file_ext}"
                    file_path = os.path.join(upload_dir, unique_filename)

                    # Save file with size limit
                    content = await file.read(10 * 1024 * 1024 + 1)  # 10MB limit
                    if len(content) > 10 * 1024 * 1024:
                        continue  # Skip oversized attachments
                    with open(file_path, "wb") as buffer:
                        buffer.write(content)

                    attachment_paths.append({
                        "original_name": file.filename,
                        "path": file_path
                    })

        # Add attachment info to description
        if attachment_paths:
            task_description += "\n\n**ATTACHMENTS:**\n"
            for attachment in attachment_paths:
                task_description += f"- {attachment['original_name']}\n"

        # Create the escalation task
        escalation_task = Task(
            title=task_title,
            description=task_description,
            status="pending",
            priority=priority,
            owner_id=assigned_to_id,
            lead_id=lead_id,
            related_contact_name=borrower_name,
            related_type="escalation",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        db.add(escalation_task)
        db.commit()
        db.refresh(escalation_task)

        logger.info(
            f"Escalation created by user {current_user.id} for lead {lead_id}, "
            f"assigned to user {assigned_to_id}"
        )

        return {
            "success": True,
            "escalation": {
                "id": escalation_task.id,
                "title": escalation_task.title,
                "assigned_to": {
                    "id": assigned_user.id,
                    "name": assigned_user.full_name or assigned_user.email,
                    "email": assigned_user.email
                },
                "borrower": {
                    "id": lead.id,
                    "name": borrower_name,
                    "loan_number": loan_number
                },
                "priority": priority,
                "created_at": escalation_task.created_at.isoformat(),
                "attachments": [a["original_name"] for a in attachment_paths]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating escalation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
