"""
Realtor Portal API Routes
Perennia AI - Mortgage CRM

Comprehensive API for the realtor portal including:
- Authentication and session management
- Loan data with real-time sync
- Letter generation and management
- Communication and messaging
- AI assistant
- SMS webhook handling
"""

import os
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/realtor-portal", tags=["Realtor Portal"])


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_date(val):
    """Format date for SQLite/PostgreSQL compatibility."""
    if val is None:
        return None
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_anthropic_client = None


def set_dependencies(get_db_func, anthropic_client=None):
    """Set dependencies from main.py."""
    global _get_db, _anthropic_client
    _get_db = get_db_func
    _anthropic_client = anthropic_client
    logger.info("Realtor Portal routes dependencies set")


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Realtor Portal routes not initialized")
    yield from _get_db()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class RealtorLoginRequest(BaseModel):
    """Login request for realtor portal."""
    email: EmailStr
    password: Optional[str] = None  # For password auth
    magic_link_token: Optional[str] = None  # For magic link auth


class RealtorLoginResponse(BaseModel):
    """Login response with session token."""
    success: bool
    token: Optional[str] = None
    realtor_id: Optional[int] = None
    name: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


class GenerateLetterRequest(BaseModel):
    """Request to generate a letter."""
    letter_type: str = Field(..., description="prequal or preapproval")
    property_address: Optional[str] = None
    purchase_price: Optional[float] = None
    approved_amount: Optional[float] = None
    custom_variables: Optional[dict] = None


class GenerateLetterResponse(BaseModel):
    """Response from letter generation."""
    success: bool
    letter_id: Optional[int] = None
    version: Optional[int] = None
    share_url: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Request to send a message to loan officer."""
    loan_id: int
    message: str
    request_callback: bool = False


class AIAssistantRequest(BaseModel):
    """Request for AI assistant."""
    loan_id: int
    question: str
    conversation_history: Optional[List[dict]] = None


class SMSWebhookPayload(BaseModel):
    """Incoming SMS webhook payload (Twilio format)."""
    From: str = Field(..., alias="From")
    Body: str
    MessageSid: Optional[str] = None


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@router.post("/auth/login", response_model=RealtorLoginResponse)
async def realtor_login(
    request: RealtorLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate a realtor and return session token.

    Supports:
    - Email/password authentication
    - Magic link token verification
    """
    if request.magic_link_token:
        # Verify magic link
        result = db.execute(text("""
            SELECT rpu.id, rpu.first_name, rpu.last_name, rpu.organization_id
            FROM realtor_magic_links rml
            JOIN realtor_portal_users rpu ON rpu.id = rml.realtor_id
            WHERE rml.token = :token
                AND rml.expires_at > CURRENT_TIMESTAMP
                AND rml.used_at IS NULL
        """), {"token": request.magic_link_token}).fetchone()

        if not result:
            return RealtorLoginResponse(
                success=False,
                error="Invalid or expired magic link"
            )

        # Mark link as used
        db.execute(text("""
            UPDATE realtor_magic_links
            SET used_at = CURRENT_TIMESTAMP
            WHERE token = :token
        """), {"token": request.magic_link_token})

    else:
        # Email/password auth
        result = db.execute(text("""
            SELECT id, first_name, last_name, organization_id, password_hash
            FROM realtor_portal_users
            WHERE email = :email AND is_active = TRUE
        """), {"email": request.email}).fetchone()

        if not result:
            return RealtorLoginResponse(
                success=False,
                error="Invalid credentials"
            )

        # Verify password (simplified - use proper hashing in production)
        if result[4] and request.password:
            import hashlib
            password_hash = hashlib.sha256(request.password.encode()).hexdigest()
            if password_hash != result[4]:
                return RealtorLoginResponse(
                    success=False,
                    error="Invalid credentials"
                )

    # Create session token
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    db.execute(text("""
        INSERT INTO realtor_sessions (realtor_id, token, expires_at)
        VALUES (:realtor_id, :token, :expires_at)
    """), {
        "realtor_id": result[0],
        "token": session_token,
        "expires_at": expires_at
    })

    # Update last login
    db.execute(text("""
        UPDATE realtor_portal_users
        SET last_login_at = CURRENT_TIMESTAMP,
            login_count = login_count + 1
        WHERE id = :id
    """), {"id": result[0]})
    db.commit()

    return RealtorLoginResponse(
        success=True,
        token=session_token,
        realtor_id=result[0],
        name=f"{result[1]} {result[2]}",
        expires_at=expires_at.isoformat()
    )


@router.post("/auth/logout")
async def realtor_logout(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Invalidate realtor session."""
    db.execute(text("""
        DELETE FROM realtor_sessions WHERE token = :token
    """), {"token": token})
    db.commit()

    return {"success": True}


# =============================================================================
# HELPER: Get Realtor from Token
# =============================================================================

async def get_current_realtor(
    token: str = Query(..., description="Session token"),
    db: Session = Depends(get_db)
) -> dict:
    """Validate token and return realtor info."""
    result = db.execute(text("""
        SELECT rs.realtor_id, rpu.organization_id, rpu.first_name, rpu.last_name
        FROM realtor_sessions rs
        JOIN realtor_portal_users rpu ON rpu.id = rs.realtor_id
        WHERE rs.token = :token
            AND rs.expires_at > CURRENT_TIMESTAMP
            AND rpu.is_active = TRUE
    """), {"token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return {
        "realtor_id": result[0],
        "organization_id": result[1],
        "name": f"{result[2]} {result[3]}"
    }


# =============================================================================
# LOAN DATA ENDPOINTS
# =============================================================================

@router.get("/loans")
async def get_realtor_loans(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get all loans the realtor has access to."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorAccessValidator
    validator = RealtorAccessValidator(db)
    loans = validator.get_accessible_loans(realtor["realtor_id"])

    return {
        "success": True,
        "loans": loans,
        "count": len(loans)
    }


@router.get("/loans/{loan_id}")
async def get_loan_details(
    loan_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get detailed loan information."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import (
        RealtorPermissionService,
        RealtorAccessValidator
    )

    # Validate access
    validator = RealtorAccessValidator(db)
    access = validator.validate_access(realtor["realtor_id"], loan_id)
    if not access["valid"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    # Record view
    validator.record_view(realtor["realtor_id"], loan_id)

    # Get permissions
    perm_service = RealtorPermissionService(db)
    permissions = perm_service.get_permissions(realtor["realtor_id"], loan_id)

    # Get loan data (compatible with both PostgreSQL and SQLite schemas)
    loan = db.execute(text("""
        SELECT
            l.id, l.stage as status, l.amount as loan_amount, l.loan_type,
            l.property_address, l.closing_date as expected_close_date,
            l.borrower_name,
            u.full_name as lo_name, u.email as lo_email, u.phone as lo_phone
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Build response based on permissions
    response = {
        "id": loan[0],
        "status": loan[1] or "unknown",
        "status_display": (loan[1] or "unknown").replace("_", " ").title(),
        "loan_amount": float(loan[2]) if loan[2] else None,
        "loan_type": loan[3],
        "property_address": loan[4] if permissions.can_view_status else None,
        "expected_close_date": format_date(loan[5]),
        "borrower_name": loan[6],
        "loan_officer": {
            "name": loan[7],
            "email": loan[8],
            "phone": loan[9]
        },
        "role": access["role"],
        "permissions": permissions.to_dict()
    }

    # Filter hidden fields
    response = perm_service.filter_loan_data(realtor["realtor_id"], loan_id, response)

    return {"success": True, "loan": response}


@router.get("/loans/{loan_id}/timeline")
async def get_loan_timeline(
    loan_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get loan timeline and milestones."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorPermissionService
    perm_service = RealtorPermissionService(db)

    if not perm_service.check_permission(realtor["realtor_id"], loan_id, "view_timeline"):
        raise HTTPException(status_code=403, detail="Timeline access not permitted")

    milestones = db.execute(text("""
        SELECT
            milestone_name, is_completed, completed_at,
            target_date, display_order
        FROM portal_milestones
        WHERE loan_id = :loan_id
        ORDER BY display_order
    """), {"loan_id": loan_id}).fetchall()

    return {
        "success": True,
        "milestones": [
            {
                "name": m[0],
                "is_completed": m[1],
                "completed_at": format_date(m[2]),
                "target_date": format_date(m[3]),
                "order": m[4]
            }
            for m in milestones
        ]
    }


@router.get("/loans/{loan_id}/conditions")
async def get_loan_conditions(
    loan_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get loan conditions (if permitted)."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorPermissionService
    perm_service = RealtorPermissionService(db)

    if not perm_service.check_permission(realtor["realtor_id"], loan_id, "view_conditions"):
        raise HTTPException(status_code=403, detail="Conditions not available for this loan stage")

    conditions = db.execute(text("""
        SELECT
            id, condition_name, category, status, description,
            due_date, created_at
        FROM loan_conditions
        WHERE loan_id = :loan_id
        ORDER BY
            CASE status WHEN 'open' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            due_date NULLS LAST
    """), {"loan_id": loan_id}).fetchall()

    return {
        "success": True,
        "conditions": [
            {
                "id": c[0],
                "name": c[1],
                "category": c[2],
                "status": c[3],
                "description": c[4],
                "due_date": format_date(c[5])
            }
            for c in conditions
        ],
        "summary": {
            "total": len(conditions),
            "open": len([c for c in conditions if c[3] == "open"]),
            "cleared": len([c for c in conditions if c[3] == "cleared"])
        }
    }


# =============================================================================
# LETTER GENERATION ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/letters", response_model=GenerateLetterResponse)
async def generate_letter(
    loan_id: int,
    request: GenerateLetterRequest,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Generate a pre-qual or pre-approval letter."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorPermissionService
    from services.realtor_letter_service import LetterGenerationService, LetterRateLimiter

    perm_service = RealtorPermissionService(db)
    action = "generate_prequal" if request.letter_type == "prequal" else "generate_preapproval"

    if not perm_service.check_permission(realtor["realtor_id"], loan_id, action):
        raise HTTPException(
            status_code=403,
            detail=f"Letter generation not permitted for this loan stage"
        )

    # Check rate limits
    rate_limiter = LetterRateLimiter(db)
    limit_check = rate_limiter.check_limit(realtor["organization_id"], request.letter_type)

    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=limit_check["reason"]
        )

    # Generate letter
    letter_service = LetterGenerationService(db)

    variables = request.custom_variables or {}
    if request.approved_amount:
        variables["prequal_amount"] = f"{request.approved_amount:,.0f}"

    result = letter_service.generate_letter(
        organization_id=realtor["organization_id"],
        loan_id=loan_id,
        letter_type=request.letter_type,
        variables=variables,
        generated_by_realtor=realtor["realtor_id"],
        property_address=request.property_address,
        purchase_price=request.purchase_price
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))

    # Increment rate limit counter
    rate_limiter.increment_usage(realtor["organization_id"], request.letter_type)

    return GenerateLetterResponse(
        success=True,
        letter_id=result["letter_id"],
        version=result["version"],
        share_url=result["share_url"],
        expires_at=result["expires_at"]
    )


@router.get("/loans/{loan_id}/letters")
async def get_loan_letters(
    loan_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get all letters for a loan."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_letter_service import LetterGenerationService

    letter_service = LetterGenerationService(db)
    letters = letter_service.get_letters_for_loan(loan_id)

    return {
        "success": True,
        "letters": letters
    }


@router.get("/letters/{letter_id}")
async def get_letter(
    letter_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get a specific letter."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_letter_service import LetterGenerationService

    letter_service = LetterGenerationService(db)
    letter = letter_service.get_letter(letter_id)

    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")

    return {"success": True, "letter": letter}


@router.get("/letters/{letter_id}/pdf")
async def download_letter_pdf(
    letter_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Download letter as PDF."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_letter_service import LetterGenerationService

    letter_service = LetterGenerationService(db)
    pdf_bytes = letter_service.generate_pdf(letter_id)

    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="PDF generation failed")

    # Record download
    letter_service.record_download(letter_id)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=letter_{letter_id}.pdf"}
    )


@router.get("/letters/shared/{share_token}")
async def get_shared_letter(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Get a letter by share token (public access)."""
    from services.realtor_letter_service import LetterGenerationService

    letter_service = LetterGenerationService(db)
    letter = letter_service.get_letter_by_share_token(share_token)

    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found or expired")

    # Record download
    letter_service.record_download(letter["id"])

    return {"success": True, "letter": letter}


# =============================================================================
# MESSAGING ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/messages")
async def send_message(
    loan_id: int,
    request: SendMessageRequest,
    token: str = Query(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Send a message to the loan officer."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorPermissionService
    perm_service = RealtorPermissionService(db)

    if not perm_service.check_permission(realtor["realtor_id"], loan_id, "send_messages"):
        raise HTTPException(status_code=403, detail="Messaging not permitted")

    # Record the message
    result = db.execute(text("""
        INSERT INTO portal_communication_events (
            organization_id, realtor_id, loan_id,
            event_type, channel, direction, content, metadata
        )
        SELECT
            l.organization_id, :realtor_id, :loan_id,
            'message', 'portal', 'inbound', :content,
            :metadata
        FROM loans l WHERE l.id = :loan_id
        RETURNING id
    """), {
        "realtor_id": realtor["realtor_id"],
        "loan_id": loan_id,
        "content": request.message,
        "metadata": f'{{"request_callback": {str(request.request_callback).lower()}}}'
    })
    message_id = result.fetchone()[0]
    db.commit()

    # TODO: Trigger notification to loan officer

    return {
        "success": True,
        "message_id": message_id,
        "message": "Message sent successfully"
    }


@router.get("/loans/{loan_id}/messages")
async def get_messages(
    loan_id: int,
    token: str = Query(...),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
):
    """Get message history for a loan."""
    realtor = await get_current_realtor(token, db)

    messages = db.execute(text("""
        SELECT
            id, event_type, channel, direction,
            content, created_at, read_at
        FROM portal_communication_events
        WHERE realtor_id = :realtor_id
            AND loan_id = :loan_id
            AND event_type = 'message'
        ORDER BY created_at DESC
        LIMIT :limit
    """), {
        "realtor_id": realtor["realtor_id"],
        "loan_id": loan_id,
        "limit": limit
    }).fetchall()

    return {
        "success": True,
        "messages": [
            {
                "id": m[0],
                "type": m[1],
                "channel": m[2],
                "direction": m[3],
                "content": m[4],
                "created_at": format_date(m[5]),
                "read_at": format_date(m[6])
            }
            for m in messages
        ]
    }


# =============================================================================
# AI ASSISTANT ENDPOINT
# =============================================================================

@router.post("/assistant")
async def ai_assistant(
    request: AIAssistantRequest,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """AI assistant for realtor questions."""
    realtor = await get_current_realtor(token, db)

    from services.realtor_ai_workflow_service import PortalAIWorkflowService

    ai_service = PortalAIWorkflowService(db, _anthropic_client)

    result = await ai_service.answer_question(
        realtor_id=realtor["realtor_id"],
        loan_id=request.loan_id,
        question=request.question,
        conversation_history=request.conversation_history
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {
        "success": True,
        "answer": result["answer"]
    }


# =============================================================================
# SMS WEBHOOK ENDPOINT
# =============================================================================

@router.post("/webhooks/sms")
async def handle_sms_webhook(
    payload: SMSWebhookPayload,
    db: Session = Depends(get_db)
):
    """
    Handle incoming SMS webhook (from Twilio).

    This endpoint processes SMS commands from realtors.
    """
    from services.realtor_ai_workflow_service import PortalAIWorkflowService

    ai_service = PortalAIWorkflowService(db, _anthropic_client)

    result = await ai_service.process_sms_command(
        phone_number=payload.From,
        message=payload.Body
    )

    # Return TwiML response
    from fastapi.responses import Response

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{result.get('response', 'Message received.')}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# =============================================================================
# CRM WEBHOOK ENDPOINT
# =============================================================================

@router.post("/webhooks/crm/{webhook_type}")
async def handle_crm_webhook(
    webhook_type: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Handle CRM webhooks for real-time updates.

    Supported webhook types:
    - loan.status_changed
    - loan.updated
    - loan.document_added
    - loan.document_status_changed
    - loan.milestone_completed
    - loan.condition_updated
    """
    from services.realtor_crm_sync_service import CRMWebhookProcessor, realtor_sync_manager

    processor = CRMWebhookProcessor(realtor_sync_manager, db)
    result = await processor.process_webhook(webhook_type, payload)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@router.websocket("/ws/{token}")
async def realtor_websocket(
    websocket: WebSocket,
    token: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time loan updates.

    Connect with: ws://host/api/v1/realtor-portal/ws/{session_token}
    """
    from services.realtor_crm_sync_service import realtor_sync_manager
    from services.realtor_permission_service import RealtorAccessValidator

    # Validate token
    result = db.execute(text("""
        SELECT rs.realtor_id FROM realtor_sessions rs
        WHERE rs.token = :token AND rs.expires_at > CURRENT_TIMESTAMP
    """), {"token": token}).fetchone()

    if not result:
        await websocket.close(code=4001, reason="Invalid or expired session")
        return

    realtor_id = result[0]

    # Get accessible loans
    validator = RealtorAccessValidator(db)
    loans = validator.get_accessible_loans(realtor_id)
    loan_ids = [loan["loan_id"] for loan in loans]

    # Connect with metadata
    await realtor_sync_manager.connect(
        websocket=websocket,
        realtor_id=realtor_id,
        loan_ids=loan_ids,
        metadata={
            "ip_address": websocket.client.host if websocket.client else None,
        }
    )

    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            import json
            try:
                message = json.loads(data)

                # Handle subscribe/unsubscribe
                if message.get("type") == "SUBSCRIBE" and message.get("loan_id"):
                    # Validate access before subscribing
                    access = validator.validate_access(realtor_id, message["loan_id"])
                    if access["valid"]:
                        await realtor_sync_manager.subscribe_to_loan(
                            realtor_id, message["loan_id"]
                        )

                elif message.get("type") == "UNSUBSCRIBE" and message.get("loan_id"):
                    await realtor_sync_manager.unsubscribe_from_loan(
                        realtor_id, message["loan_id"]
                    )

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from realtor {realtor_id}")

    except WebSocketDisconnect:
        await realtor_sync_manager.disconnect(realtor_id)
    except Exception as e:
        logger.error(f"WebSocket error for realtor {realtor_id}: {e}")
        await realtor_sync_manager.disconnect(realtor_id)


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/me")
async def get_realtor_profile(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get current realtor's profile."""
    realtor = await get_current_realtor(token, db)

    profile = db.execute(text("""
        SELECT
            id, email, phone, first_name, last_name,
            brokerage_name, license_number, license_state,
            notification_preferences, last_login_at, login_count
        FROM realtor_portal_users
        WHERE id = :id
    """), {"id": realtor["realtor_id"]}).fetchone()

    return {
        "success": True,
        "profile": {
            "id": profile[0],
            "email": profile[1],
            "phone": profile[2],
            "first_name": profile[3],
            "last_name": profile[4],
            "brokerage_name": profile[5],
            "license_number": profile[6],
            "license_state": profile[7],
            "notification_preferences": profile[8],
            "last_login": format_date(profile[9]),
            "login_count": profile[10]
        }
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "realtor-portal"}


@router.post("/admin/create-test-realtor")
async def create_test_realtor(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """
    Create a test realtor account for testing purposes.
    Requires admin API key for authorization.
    """
    import os
    import traceback
    expected_key = os.getenv("ADMIN_API_KEY", "perennia-admin-2024")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    test_email = "test.realtor@perenniaai.com"
    realtor_id = None

    try:
        # Step 1: Check if already exists
        logger.info("Step 1: Checking for existing realtor")
        existing = db.execute(text("""
            SELECT id, email FROM realtor_portal_users WHERE email = :email
        """), {"email": test_email}).fetchone()

        if existing:
            realtor_id = existing[0]
            logger.info(f"Test realtor already exists: {realtor_id}")
        else:
            # Step 2: Get organization
            logger.info("Step 2: Getting organization")
            org = db.execute(text("SELECT id FROM organizations LIMIT 1")).fetchone()
            org_id = org[0] if org else 1
            logger.info(f"Using org_id: {org_id}")

            # Step 3: Get an LO
            logger.info("Step 3: Getting LO")
            lo = db.execute(text("""
                SELECT id FROM users WHERE role IN ('loan_officer', 'admin', 'sales') LIMIT 1
            """)).fetchone()
            lo_id = lo[0] if lo else None
            logger.info(f"Using lo_id: {lo_id}")

            # Step 4: Create realtor
            logger.info("Step 4: Creating realtor")
            result = db.execute(text("""
                INSERT INTO realtor_portal_users (
                    organization_id, email, phone, first_name, last_name,
                    brokerage_name, license_number, license_state,
                    primary_lo_id, is_active, created_at
                ) VALUES (
                    :org_id, :email, '555-TEST-001', 'Test', 'Realtor',
                    'Perennia Test Realty', 'TEST12345', 'CA',
                    :lo_id, TRUE, CURRENT_TIMESTAMP
                ) RETURNING id
            """), {"org_id": org_id, "email": test_email, "lo_id": lo_id})
            realtor_id = result.fetchone()[0]
            db.commit()
            logger.info(f"Created test realtor: {realtor_id}")

        # Step 5: Create session token
        logger.info("Step 5: Creating session token")
        session_token = f"test-prod-{secrets.token_urlsafe(24)}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        # Step 6: Remove old sessions
        logger.info("Step 6: Removing old sessions")
        db.execute(text("""
            DELETE FROM realtor_portal_sessions WHERE realtor_id = :rid
        """), {"rid": realtor_id})

        # Step 7: Create new session
        logger.info("Step 7: Creating new session")
        db.execute(text("""
            INSERT INTO realtor_portal_sessions (
                realtor_id, token, expires_at, ip_address, user_agent, created_at
            ) VALUES (
                :rid, :token, :exp, '0.0.0.0', 'Admin API', CURRENT_TIMESTAMP
            )
        """), {"rid": realtor_id, "token": session_token, "exp": expires_at})
        db.commit()

        # Step 8: Associate with recent loans
        logger.info("Step 8: Associating with loans")
        loans = db.execute(text("""
            SELECT l.id, l.borrower_name FROM loans l
            WHERE l.id NOT IN (
                SELECT loan_id FROM realtor_loan_associations WHERE realtor_id = :rid
            )
            ORDER BY l.id DESC LIMIT 5
        """), {"rid": realtor_id}).fetchall()

        associated_loans = []
        for loan in loans:
            db.execute(text("""
                INSERT INTO realtor_loan_associations (
                    realtor_id, loan_id, role, access_granted_at
                ) VALUES (:rid, :lid, 'buyer_agent', CURRENT_TIMESTAMP)
            """), {"rid": realtor_id, "lid": loan[0]})
            associated_loans.append({"id": loan[0], "borrower": loan[1]})
        db.commit()

        logger.info("Test realtor creation complete")
        return {
            "success": True,
            "realtor_id": realtor_id,
            "email": test_email,
            "token": session_token,
            "expires_at": expires_at.isoformat(),
            "associated_loans": associated_loans,
            "test_urls": {
                "profile": f"https://api.perenniaai.com/api/v1/realtor-portal/me?token={session_token}",
                "loans": f"https://api.perenniaai.com/api/v1/realtor-portal/loans?token={session_token}"
            }
        }

    except Exception as e:
        db.rollback()
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        logger.error(f"Error creating test realtor: {error_msg}\n{stack_trace}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_msg,
                "step": "See logs for step info",
                "traceback": stack_trace.split('\n')[-5:]
            }
        )
