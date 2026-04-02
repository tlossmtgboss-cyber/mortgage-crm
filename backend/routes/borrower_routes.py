"""
Borrower Portal Routes

API endpoints for borrower-facing mortgage application functionality:
- Application management (create, update, resume, submit)
- Document upload and management
- Co-borrower invitations
- Concierge AI chat
- Review call scheduling
"""

import logging
import uuid
import json
import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr

from database import get_db
from services.notification_service import NotificationService
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/borrower", tags=["Borrower Portal"])


def safe_isoformat(dt):
    """Safely format a datetime, handling both datetime objects and strings."""
    if dt is None:
        return None
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)  # Already a string (SQLite)


# =============================================================================
# AUTHENTICATION DEPENDENCY
# =============================================================================

def get_borrower_from_token(request: Request, db: Session = Depends(get_db)) -> dict:
    """Extract and verify borrower from JWT token."""
    import jwt
    import os

    JWT_SECRET = os.getenv("JWT_SECRET")
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET not configured")

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False})
        if payload.get("type") != "borrower":
            raise HTTPException(status_code=401, detail="Invalid token type")

        borrower_id = payload.get("sub")

        # Fetch borrower from database
        result = db.execute(text("""
            SELECT id, email, first_name, last_name, profile_photo,
                   communication_consent, marketing_consent
            FROM borrower_profiles
            WHERE id = :id
        """), {"id": borrower_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Borrower not found")

        return {
            "id": result[0],
            "email": result[1],
            "first_name": result[2],
            "last_name": result[3],
            "profile_photo": result[4],
            "communication_consent": result[5],
            "marketing_consent": result[6],
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateApplicationRequest(BaseModel):
    loan_purpose: str  # purchase, refinance, cash_out
    property_type: Optional[str] = "single_family"
    lo_id: Optional[int] = None


class UpdateApplicationRequest(BaseModel):
    current_step: Optional[str] = None
    profile_data: Optional[dict] = None
    income_data: Optional[dict] = None
    asset_data: Optional[dict] = None
    property_data: Optional[dict] = None
    declarations: Optional[dict] = None


class CoBorrowerInviteRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    relationship: str  # spouse, partner, family, other


class ScheduleCallRequest(BaseModel):
    preferred_date: str
    preferred_time: str
    timezone: Optional[str] = "America/New_York"
    notes: Optional[str] = None


class ConciergeMessageRequest(BaseModel):
    message: str
    application_id: Optional[str] = None


# =============================================================================
# APPLICATION ROUTES
# =============================================================================

@router.post("/applications")
async def create_application(
    request: CreateApplicationRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Create a new mortgage application."""
    borrower = get_borrower_from_token(req, db)

    application_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.execute(text("""
        INSERT INTO borrower_applications (
            id, borrower_profile_id, loan_purpose, property_type,
            status, current_step, progress_percentage,
            lo_id, created_at, updated_at
        ) VALUES (
            :id, :borrower_id, :loan_purpose, :property_type,
            'in_progress', 'profile', 0,
            :lo_id, :created_at, :updated_at
        )
    """), {
        "id": application_id,
        "borrower_id": borrower["id"],
        "loan_purpose": request.loan_purpose,
        "property_type": request.property_type,
        "lo_id": request.lo_id,
        "created_at": now,
        "updated_at": now,
    })
    db.commit()

    return {
        "id": application_id,
        "status": "in_progress",
        "current_step": "profile",
        "progress_percentage": 0,
        "created_at": now.isoformat(),
    }


@router.get("/applications")
async def list_applications(
    req: Request,
    db: Session = Depends(get_db),
):
    """List all applications for the current borrower."""
    borrower = get_borrower_from_token(req, db)

    results = db.execute(text("""
        SELECT id, loan_purpose, property_type, status, current_step,
               progress_percentage, created_at, updated_at
        FROM borrower_applications
        WHERE borrower_profile_id = :borrower_id
        ORDER BY updated_at DESC
    """), {"borrower_id": borrower["id"]}).fetchall()

    return {
        "applications": [
            {
                "id": r[0],
                "loan_purpose": r[1],
                "property_type": r[2],
                "status": r[3],
                "current_step": r[4],
                "progress_percentage": r[5],
                "created_at": safe_isoformat(r[6]),
                "updated_at": safe_isoformat(r[7]),
            }
            for r in results
        ]
    }


@router.get("/applications/{application_id}")
async def get_application(
    application_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """Get a specific application with all data."""
    borrower = get_borrower_from_token(req, db)

    result = db.execute(text("""
        SELECT id, loan_purpose, property_type, status, current_step,
               progress_percentage, profile_data, income_data, asset_data,
               property_data, declarations, created_at, updated_at
        FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Application not found")

    return {
        "id": result[0],
        "loan_purpose": result[1],
        "property_type": result[2],
        "status": result[3],
        "current_step": result[4],
        "progress_percentage": result[5],
        "profile_data": json.loads(result[6]) if result[6] else {},
        "income_data": json.loads(result[7]) if result[7] else {},
        "asset_data": json.loads(result[8]) if result[8] else {},
        "property_data": json.loads(result[9]) if result[9] else {},
        "declarations": json.loads(result[10]) if result[10] else {},
        "created_at": safe_isoformat(result[11]),
        "updated_at": safe_isoformat(result[12]),
    }


@router.patch("/applications/{application_id}")
async def update_application(
    application_id: str,
    request: UpdateApplicationRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Update application data (auto-save)."""
    borrower = get_borrower_from_token(req, db)

    # Verify ownership
    existing = db.execute(text("""
        SELECT id, progress_percentage FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Application not found")

    # Build dynamic update
    updates = ["updated_at = :updated_at"]
    params = {"id": application_id, "updated_at": datetime.now(timezone.utc)}

    if request.current_step:
        updates.append("current_step = :current_step")
        params["current_step"] = request.current_step

        # Calculate progress based on step
        step_progress = {
            "profile": 20,
            "income": 40,
            "assets": 60,
            "property": 80,
            "declarations": 90,
            "review": 95,
            "submitted": 100,
        }
        if request.current_step in step_progress:
            updates.append("progress_percentage = :progress")
            params["progress"] = step_progress[request.current_step]

    if request.profile_data:
        updates.append("profile_data = :profile_data")
        params["profile_data"] = json.dumps(request.profile_data)

    if request.income_data:
        updates.append("income_data = :income_data")
        params["income_data"] = json.dumps(request.income_data)

    if request.asset_data:
        updates.append("asset_data = :asset_data")
        params["asset_data"] = json.dumps(request.asset_data)

    if request.property_data:
        updates.append("property_data = :property_data")
        params["property_data"] = json.dumps(request.property_data)

    if request.declarations:
        updates.append("declarations = :declarations")
        params["declarations"] = json.dumps(request.declarations)

    query = "UPDATE borrower_applications SET " + ", ".join(updates) + " WHERE id = :id"
    db.execute(text(query), params)
    db.commit()

    return {"success": True, "message": "Application updated"}


@router.post("/applications/{application_id}/submit")
async def submit_application(
    application_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """Submit application for review."""
    borrower = get_borrower_from_token(req, db)

    # Verify ownership and get application data
    app = db.execute(text("""
        SELECT id, status, profile_data, income_data, asset_data,
               property_data, declarations, lo_id
        FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app[1] == "submitted":
        raise HTTPException(status_code=400, detail="Application already submitted")

    now = datetime.now(timezone.utc)

    # Update application status
    db.execute(text("""
        UPDATE borrower_applications
        SET status = 'submitted', current_step = 'submitted',
            progress_percentage = 100, submitted_at = :submitted_at,
            updated_at = :updated_at
        WHERE id = :id
    """), {"id": application_id, "submitted_at": now, "updated_at": now})

    db.commit()

    return {
        "success": True,
        "message": "Application submitted successfully",
        "submitted_at": now.isoformat(),
    }


# =============================================================================
# DOCUMENT ROUTES
# =============================================================================

@router.get("/applications/{application_id}/documents")
async def list_documents(
    application_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """List all documents for an application."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    docs = db.execute(text("""
        SELECT id, doc_type, doc_category, filename, file_size,
               status, uploaded_at, review_notes
        FROM borrower_documents
        WHERE application_id = :application_id
        ORDER BY uploaded_at DESC
    """), {"application_id": application_id}).fetchall()

    return {
        "documents": [
            {
                "id": d[0],
                "doc_type": d[1],
                "doc_category": d[2],
                "filename": d[3],
                "file_size": d[4],
                "status": d[5],
                "uploaded_at": safe_isoformat(d[6]),
                "review_notes": d[7],
            }
            for d in docs
        ]
    }


@router.post("/applications/{application_id}/documents")
async def upload_document(
    application_id: str,
    req: Request,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    doc_category: str = Form("other"),
    db: Session = Depends(get_db),
):
    """Upload a document for an application."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Read file content with size and type validation
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
    ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg",
                     "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PDF, images, Word documents.")
    content = await file.read()
    file_size = len(content)
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    # Store document
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.execute(text("""
        INSERT INTO borrower_documents (
            id, application_id, borrower_id, doc_type, doc_category,
            filename, original_filename, file_size, mime_type,
            file_content, status, uploaded_at
        ) VALUES (
            :id, :application_id, :borrower_id, :doc_type, :doc_category,
            :filename, :original_filename, :file_size, :mime_type,
            :file_content, 'pending_review', :uploaded_at
        )
    """), {
        "id": doc_id,
        "application_id": application_id,
        "borrower_id": borrower["id"],
        "doc_type": doc_type,
        "doc_category": doc_category,
        "filename": f"{doc_id}_{file.filename}",
        "original_filename": file.filename,
        "file_size": file_size,
        "mime_type": file.content_type,
        "file_content": base64.b64encode(content).decode('utf-8'),
        "uploaded_at": now,
    })
    db.commit()

    return {
        "id": doc_id,
        "filename": file.filename,
        "doc_type": doc_type,
        "status": "pending_review",
        "uploaded_at": now.isoformat(),
    }


@router.delete("/applications/{application_id}/documents/{document_id}")
async def delete_document(
    application_id: str,
    document_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """Delete a document from an application."""
    borrower = get_borrower_from_token(req, db)

    # Verify ownership
    doc = db.execute(text("""
        SELECT d.id FROM borrower_documents d
        JOIN borrower_applications a ON a.id = d.application_id
        WHERE d.id = :doc_id AND d.application_id = :app_id
              AND a.borrower_profile_id = :borrower_id
    """), {
        "doc_id": document_id,
        "app_id": application_id,
        "borrower_id": borrower["id"],
    }).fetchone()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.execute(text("DELETE FROM borrower_documents WHERE id = :id"), {"id": document_id})
    db.commit()

    return {"success": True, "message": "Document deleted"}


# =============================================================================
# CO-BORROWER ROUTES
# =============================================================================

@router.get("/applications/{application_id}/coborrowers")
async def list_coborrowers(
    application_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """List co-borrowers for an application."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    coborrowers = db.execute(text("""
        SELECT id, email, first_name, last_name, relationship,
               status, invited_at, completed_at
        FROM coborrower_invitations
        WHERE application_id = :application_id
        ORDER BY invited_at DESC
    """), {"application_id": application_id}).fetchall()

    return {
        "coborrowers": [
            {
                "id": c[0],
                "email": c[1],
                "first_name": c[2],
                "last_name": c[3],
                "relationship": c[4],
                "status": c[5],
                "invited_at": safe_isoformat(c[6]),
                "completed_at": safe_isoformat(c[7]),
            }
            for c in coborrowers
        ]
    }


@router.post("/applications/{application_id}/coborrowers")
async def invite_coborrower(
    application_id: str,
    request: CoBorrowerInviteRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Invite a co-borrower to the application."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Create invitation
    import secrets
    invitation_id = str(uuid.uuid4())
    invitation_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    db.execute(text("""
        INSERT INTO coborrower_invitations (
            id, application_id, email, first_name, last_name,
            relationship, invitation_token, status, invited_at, expires_at
        ) VALUES (
            :id, :application_id, :email, :first_name, :last_name,
            :relationship, :invitation_token, 'pending', :invited_at, :expires_at
        )
    """), {
        "id": invitation_id,
        "application_id": application_id,
        "email": request.email,
        "first_name": request.first_name,
        "last_name": request.last_name,
        "relationship": request.relationship,
        "invitation_token": invitation_token,
        "invited_at": now,
        "expires_at": expires_at,
    })
    db.commit()

    # Send invitation email to co-borrower
    email_sent = False
    try:
        frontend_url = os.getenv("FRONTEND_URL", "https://perenniaai.com")
        accept_url = f"{frontend_url}/borrower/coborrower-accept?token={invitation_token}"

        # Get primary borrower's name for context
        primary_name = f"{borrower.get('first_name', '')} {borrower.get('last_name', '')}".strip() or "your partner"

        notification_service = NotificationService()
        notification_service.send_email(
            to_email=request.email,
            subject=f"You've been invited as a Co-Borrower on a Mortgage Application",
            html_content=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #1e40af;">Co-Borrower Invitation</h2>
                <p>Hi {request.first_name},</p>
                <p><strong>{primary_name}</strong> has invited you to join their mortgage application as a co-borrower.</p>
                <p>As a co-borrower, you'll need to provide your personal and financial information to complete the application.</p>

                <div style="margin: 30px 0; text-align: center;">
                    <a href="{accept_url}"
                       style="background: #1e40af; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-size: 16px;">
                        Accept Invitation
                    </a>
                </div>

                <p style="color: #6b7280; font-size: 14px;">This invitation expires on {expires_at.strftime('%B %d, %Y')}.</p>
                <p style="color: #6b7280; font-size: 14px;">If you have questions, please contact the primary borrower or your loan officer.</p>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="color: #9ca3af; font-size: 12px;">
                    If you didn't expect this invitation, please ignore this email.
                </p>
            </div>
            """
        )
        email_sent = True
        logger.info(f"Sent co-borrower invitation email to {request.email}")
    except Exception as email_err:
        logger.error(f"Failed to send co-borrower invitation email: {email_err}")
        # Don't fail the invitation creation just because email failed

    return {
        "id": invitation_id,
        "email": request.email,
        "status": "pending",
        "invited_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "email_sent": email_sent,
    }


@router.get("/coborrower/accept")
async def accept_coborrower_invitation(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Accept a co-borrower invitation via token."""
    result = db.execute(text("""
        SELECT id, application_id, email, first_name, last_name,
               status, expires_at
        FROM coborrower_invitations
        WHERE invitation_token = :token
    """), {"token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if result[5] == "completed":
        raise HTTPException(status_code=400, detail="Invitation already accepted")

    if result[6] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")

    # Update invitation status
    db.execute(text("""
        UPDATE coborrower_invitations
        SET status = 'accepted', accepted_at = :accepted_at
        WHERE id = :id
    """), {"id": result[0], "accepted_at": datetime.now(timezone.utc)})
    db.commit()

    return {
        "success": True,
        "application_id": result[1],
        "email": result[2],
        "first_name": result[3],
        "last_name": result[4],
    }


# =============================================================================
# CONCIERGE ROUTES
# =============================================================================

@router.post("/concierge/chat")
async def concierge_chat(
    request: ConciergeMessageRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Send a message to the AI concierge."""
    borrower = get_borrower_from_token(req, db)

    # Get application context if provided
    context = {}
    if request.application_id:
        app = db.execute(text("""
            SELECT loan_purpose, property_type, current_step, profile_data
            FROM borrower_applications
            WHERE id = :id AND borrower_profile_id = :borrower_id
        """), {"id": request.application_id, "borrower_id": borrower["id"]}).fetchone()

        if app:
            context = {
                "loan_purpose": app[0],
                "property_type": app[1],
                "current_step": app[2],
                "profile_data": json.loads(app[3]) if app[3] else {},
            }

    # Simple AI response (in production, use Claude/OpenAI)
    response_text = generate_concierge_response(request.message, context, borrower)

    # Store conversation
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.execute(text("""
        INSERT INTO concierge_messages (
            id, borrower_id, application_id, role, content, created_at
        ) VALUES
            (:user_id, :borrower_id, :app_id, 'user', :user_message, :created_at),
            (:assistant_id, :borrower_id, :app_id, 'assistant', :assistant_message, :created_at)
    """), {
        "user_id": message_id,
        "assistant_id": str(uuid.uuid4()),
        "borrower_id": borrower["id"],
        "app_id": request.application_id,
        "user_message": request.message,
        "assistant_message": response_text,
        "created_at": now,
    })
    db.commit()

    return {
        "response": response_text,
        "timestamp": now.isoformat(),
    }


def generate_concierge_response(message: str, context: dict, borrower: dict) -> str:
    """Generate a concierge response (placeholder for AI integration)."""
    message_lower = message.lower()

    if "status" in message_lower or "where" in message_lower:
        step = context.get("current_step", "starting")
        return f"Hi {borrower.get('first_name', 'there')}! Your application is currently at the '{step}' step. Would you like help completing it?"

    if "document" in message_lower:
        return "For your application, you'll typically need: pay stubs (last 30 days), W-2s (last 2 years), bank statements (last 2 months), and a government-issued ID. Would you like to upload any documents now?"

    if "rate" in message_lower or "interest" in message_lower:
        return "Current mortgage rates vary based on your credit score, down payment, and loan type. Your loan officer will provide personalized rate quotes once we review your application. Is there anything specific about rates you'd like to know?"

    if "help" in message_lower:
        return f"Of course, {borrower.get('first_name', 'I')}! I'm here to help with your mortgage application. You can ask me about:\n- Application status\n- Required documents\n- Rates and terms\n- Next steps\n\nWhat would you like to know?"

    return f"Thanks for your message! I'm your AI mortgage assistant. I can help you with your application, answer questions about documents needed, or explain the mortgage process. How can I assist you today?"


@router.get("/concierge/history")
async def get_concierge_history(
    application_id: Optional[str] = None,
    limit: int = Query(50, le=100),
    req: Request = None,
    db: Session = Depends(get_db),
):
    """Get conversation history with the concierge."""
    borrower = get_borrower_from_token(req, db)

    query = """
        SELECT id, role, content, created_at
        FROM concierge_messages
        WHERE borrower_id = :borrower_id
    """
    params = {"borrower_id": borrower["id"], "limit": limit}

    if application_id:
        query += " AND application_id = :app_id"
        params["app_id"] = application_id

    query += " ORDER BY created_at DESC LIMIT :limit"

    messages = db.execute(text(query), params).fetchall()

    return {
        "messages": [
            {
                "id": m[0],
                "role": m[1],
                "content": m[2],
                "created_at": safe_isoformat(m[3]),
            }
            for m in reversed(messages)  # Return in chronological order
        ]
    }


# =============================================================================
# SCHEDULING ROUTES
# =============================================================================

@router.post("/applications/{application_id}/schedule")
async def schedule_review_call(
    application_id: str,
    request: ScheduleCallRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Schedule a review call with a loan officer."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id, lo_id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Create scheduled call
    call_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.execute(text("""
        INSERT INTO scheduled_calls (
            id, application_id, borrower_id, lo_id,
            preferred_date, preferred_time, timezone,
            notes, status, created_at
        ) VALUES (
            :id, :application_id, :borrower_id, :lo_id,
            :preferred_date, :preferred_time, :timezone,
            :notes, 'pending', :created_at
        )
    """), {
        "id": call_id,
        "application_id": application_id,
        "borrower_id": borrower["id"],
        "lo_id": app[1],
        "preferred_date": request.preferred_date,
        "preferred_time": request.preferred_time,
        "timezone": request.timezone,
        "notes": request.notes,
        "created_at": now,
    })
    db.commit()

    return {
        "id": call_id,
        "preferred_date": request.preferred_date,
        "preferred_time": request.preferred_time,
        "status": "pending",
        "message": "Your call request has been submitted. A loan officer will confirm the time shortly.",
    }


@router.get("/applications/{application_id}/schedule")
async def get_scheduled_calls(
    application_id: str,
    req: Request,
    db: Session = Depends(get_db),
):
    """Get scheduled calls for an application."""
    borrower = get_borrower_from_token(req, db)

    # Verify application ownership
    app = db.execute(text("""
        SELECT id FROM borrower_applications
        WHERE id = :id AND borrower_profile_id = :borrower_id
    """), {"id": application_id, "borrower_id": borrower["id"]}).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    calls = db.execute(text("""
        SELECT id, preferred_date, preferred_time, timezone,
               confirmed_datetime, status, notes, created_at
        FROM scheduled_calls
        WHERE application_id = :application_id
        ORDER BY created_at DESC
    """), {"application_id": application_id}).fetchall()

    return {
        "scheduled_calls": [
            {
                "id": c[0],
                "preferred_date": c[1],
                "preferred_time": c[2],
                "timezone": c[3],
                "confirmed_datetime": safe_isoformat(c[4]),
                "status": c[5],
                "notes": c[6],
                "created_at": safe_isoformat(c[7]),
            }
            for c in calls
        ]
    }
