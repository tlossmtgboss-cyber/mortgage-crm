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
import json
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Header, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from services.notification_service import NotificationService
from sqlalchemy.exc import SQLAlchemyError

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

from db import get_db
from auth.dependencies import get_current_user

_anthropic_client = None


def set_dependencies(get_db_func, anthropic_client=None):
    """Set dependencies from main.py."""
    global _anthropic_client
    _anthropic_client = anthropic_client
    logger.info("Realtor Portal routes dependencies set")


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
    """Incoming SMS webhook payload (Telnyx format)."""
    From: str = Field(..., alias="From")
    Body: str
    MessageSid: Optional[str] = None


class PartnerNoteRequest(BaseModel):
    """Request to add a partner note to a client/lead."""
    content: str = Field(..., min_length=1, max_length=2000)


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@router.post("/auth/login", response_model=RealtorLoginResponse)
async def realtor_login(
    http_request: Request,
    request: RealtorLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate a realtor and return session token.

    Supports:
    - Email/password authentication
    - Magic link token verification
    """
    # Rate limit realtor login — 5/minute and 20/hour per IP
    from routes.auth_routes import (
        _get_real_client_ip, _check_auth_rate_limit_multi, _raise_rate_limit,
        _AUTH_RATE_MAX_LOGIN, _AUTH_RATE_WINDOW,
        _AUTH_RATE_MAX_LOGIN_HOUR, _AUTH_RATE_WINDOW_HOUR,
    )
    client_ip = _get_real_client_ip(http_request)
    allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
        (_AUTH_RATE_MAX_LOGIN, _AUTH_RATE_WINDOW, "realtor_login"),
        (_AUTH_RATE_MAX_LOGIN_HOUR, _AUTH_RATE_WINDOW_HOUR, "realtor_login_hour"),
    ])
    if not allowed:
        logger.warning(f"Realtor login rate limit exceeded for {client_ip}")
        _raise_rate_limit(retry_after, "Too many login attempts. Please try again later.")

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

        # Verify password
        if result[4] and request.password:
            import bcrypt as _bcrypt
            # Support legacy SHA-256 hashes (64-char hex) and bcrypt
            if len(result[4]) == 64:
                import hashlib
                if hashlib.sha256(request.password.encode()).hexdigest() != result[4]:
                    return RealtorLoginResponse(success=False, error="Invalid credentials")
                # Upgrade to bcrypt on successful login
                new_hash = _bcrypt.hashpw(request.password.encode(), _bcrypt.gensalt()).decode()
                db.execute(text("UPDATE realtor_portal_users SET password_hash = :h WHERE id = :id"),
                           {"h": new_hash, "id": result[0]})
            else:
                if not _bcrypt.checkpw(request.password.encode(), result[4].encode()):
                    return RealtorLoginResponse(success=False, error="Invalid credentials")

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
        FROM realtor_portal_sessions rs
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
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Download letter as PDF. Accepts token via query param or Authorization header."""
    # Extract token from Authorization header if not provided as query param
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization[7:]
        else:
            auth_token = authorization

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get letter directly from database (simpler than using service which has complex joins)
    letter = db.execute(text("""
        SELECT id, generated_html, download_count
        FROM pre_approval_letters
        WHERE id = :letter_id
    """), {"letter_id": letter_id}).fetchone()

    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")

    html_content = letter[1]
    if not html_content:
        raise HTTPException(status_code=500, detail="Letter has no content")

    # Return HTML as downloadable file (client-side PDF generation preferred)
    pdf_bytes = html_content.encode("utf-8")

    # Record download
    try:
        db.execute(text("""
            UPDATE pre_approval_letters
            SET download_count = COALESCE(download_count, 0) + 1,
                last_downloaded_at = CURRENT_TIMESTAMP
            WHERE id = :letter_id
        """), {"letter_id": letter_id})
        db.commit()
    except SQLAlchemyError as e:
        logger.error(f"Error recording download: {e}")

    # Determine content type based on what we're returning
    content_type = "application/pdf" if pdf_bytes and pdf_bytes[:4] == b'%PDF' else "text/html"
    filename_ext = "pdf" if content_type == "application/pdf" else "html"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename=letter_{letter_id}.{filename_ext}"}
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
# PRE-APPROVAL LETTER ENDPOINTS (FOR PARTNER PORTAL)
# =============================================================================

class GeneratePreApprovalRequest(BaseModel):
    """Request to generate a pre-approval letter."""
    include_property_address: bool = False
    property_address: Optional[str] = None
    include_purchase_price: bool = False
    purchase_price: Optional[float] = None
    calculated_loan_amount: Optional[float] = None
    partner_id: Optional[int] = None


class NotifyOverLimitRequest(BaseModel):
    """Request to notify LO about over-limit pre-approval request."""
    lead_id: int
    partner_id: Optional[int] = None
    requested_purchase_price: float
    max_approved_amount: float
    max_purchase_price: float
    borrower_name: Optional[str] = None


@router.post("/leads/{lead_id}/generate-preapproval")
async def generate_preapproval_for_lead(
    lead_id: int,
    request: GeneratePreApprovalRequest,
    authorization: str = None,
    db: Session = Depends(get_db)
):
    """
    Generate a pre-approval letter for a lead.

    This endpoint works with both CRM JWT tokens and partner portal tokens.
    """
    logger.info(f"Generating pre-approval letter for lead {lead_id}")

    # Get lead data
    lead = db.execute(text("""
        SELECT
            l.id, l.name, l.email, l.phone, l.loan_amount, l.loan_type,
            l.address, l.city, l.state, l.zip_code, l.credit_score,
            l.property_type, l.ltv, l.down_payment, l.interest_rate,
            l.stage, l.owner_id
        FROM leads l
        WHERE l.id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get organization_id from the lead's owner
    org_id = 1  # Default
    if lead[16]:  # owner_id
        owner = db.execute(text("SELECT organization_id FROM users WHERE id = :uid"), {"uid": lead[16]}).fetchone()
        if owner and owner[0]:
            org_id = owner[0]

    # Get organization info (only columns that exist)
    org = db.execute(text("""
        SELECT id, name
        FROM organizations
        WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()

    # Get LO info if owner assigned
    lo_info = None
    if lead[16]:  # owner_id
        lo = db.execute(text("""
            SELECT id, full_name, email, phone, nmls_id
            FROM users
            WHERE id = :user_id
        """), {"user_id": lead[16]}).fetchone()
        if lo:
            lo_info = {
                "name": lo[1],
                "email": lo[2],
                "phone": lo[3],
                "nmls": lo[4]
            }

    # Calculate loan amount based on LTV if purchase price provided
    approved_amount = lead[4] or 0
    purchase_price = request.purchase_price
    calculated_amount = request.calculated_loan_amount or approved_amount

    # Format property address
    property_address = request.property_address
    if not property_address and (lead[6] or lead[7]):
        parts = []
        if lead[6]:
            parts.append(lead[6])
        if lead[7]:
            parts.append(lead[7])
        if lead[8]:
            parts.append(lead[8])
        if lead[9]:
            parts.append(lead[9])
        property_address = ", ".join(parts)

    # Generate expiration date (90 days)
    expiration_date = datetime.now(timezone.utc) + timedelta(days=90)

    # Build letter HTML
    letter_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 40px; }}
            .header {{ text-align: center; border-bottom: 2px solid #1e40af; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h1 {{ color: #1e40af; margin: 0; }}
            .header p {{ color: #666; margin: 5px 0 0; }}
            .date {{ text-align: right; color: #666; margin-bottom: 20px; }}
            .salutation {{ margin-bottom: 20px; }}
            .body-text {{ margin-bottom: 15px; }}
            .amount-highlight {{ background: #f0f9ff; border: 1px solid #bfdbfe; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .amount-highlight strong {{ color: #1e40af; font-size: 1.2em; }}
            .details {{ margin: 20px 0; }}
            .details dt {{ font-weight: bold; color: #555; }}
            .details dd {{ margin: 0 0 10px 20px; }}
            .disclaimer {{ font-size: 0.85em; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
            .signature {{ margin-top: 40px; }}
            .signature-name {{ font-weight: bold; }}
            .signature-title {{ color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{org[1] if org else 'Mortgage Company'}</h1>
            <p>NMLS #{lo_info['nmls'] if lo_info and lo_info.get('nmls') else 'N/A'}</p>
        </div>

        <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>

        <div class="salutation">
            <p>To Whom It May Concern,</p>
        </div>

        <div class="body-text">
            <p>This letter confirms that <strong>{lead[1]}</strong> has applied for a mortgage loan and has been pre-approved for financing, subject to the conditions stated below.</p>
        </div>

        <div class="amount-highlight">
            <p>Pre-Approved Loan Amount: <strong>${calculated_amount:,.0f}</strong></p>
            {f'<p>Purchase Price: <strong>${purchase_price:,.0f}</strong></p>' if purchase_price else ''}
        </div>

        {f'''<div class="details">
            <dl>
                <dt>Property Address:</dt>
                <dd>{property_address}</dd>
            </dl>
        </div>''' if property_address and request.include_property_address else ''}

        <div class="details">
            <dl>
                <dt>Loan Type:</dt>
                <dd>{lead[5] or 'Conventional'}</dd>
                <dt>Property Type:</dt>
                <dd>{lead[11] or 'Single Family'}</dd>
            </dl>
        </div>

        <div class="body-text">
            <p>This pre-approval is subject to:</p>
            <ul>
                <li>Verification of information provided in the loan application</li>
                <li>Satisfactory property appraisal and title review</li>
                <li>No material change in the borrower's financial situation</li>
                <li>Compliance with all program guidelines and underwriting requirements</li>
            </ul>
        </div>

        <div class="body-text">
            <p><strong>This pre-approval is valid until {expiration_date.strftime('%B %d, %Y')}.</strong></p>
        </div>

        <div class="disclaimer">
            <p>This is not a commitment to lend. This pre-approval is based on information provided and is subject to verification. Interest rates, terms, and program availability are subject to change without notice. Additional conditions may apply based on specific program requirements.</p>
        </div>

        <div class="signature">
            <p class="signature-name">{lo_info['name'] if lo_info else 'Loan Officer'}</p>
            <p class="signature-title">Loan Officer | NMLS #{lo_info['nmls'] if lo_info and lo_info.get('nmls') else 'N/A'}</p>
            <p>{lo_info['phone'] if lo_info and lo_info.get('phone') else ''}</p>
            <p>{lo_info['email'] if lo_info and lo_info.get('email') else ''}</p>
        </div>
    </body>
    </html>
    """

    # Store the letter in database
    share_token = secrets.token_urlsafe(32)

    try:
        result = db.execute(text("""
            INSERT INTO pre_approval_letters (
                organization_id, lead_id, letter_type, version,
                generated_html, variables_used, property_address, purchase_price,
                approved_amount, expires_at, generated_by_realtor, share_token
            ) VALUES (
                :org_id, :lead_id, 'preapproval', 1,
                :html, :variables, :property_address, :purchase_price,
                :approved_amount, :expires_at, :partner_id, :share_token
            )
            RETURNING id
        """), {
            "org_id": org_id,
            "lead_id": lead_id,
            "html": letter_html,
            "variables": json.dumps({"borrower_name": lead[1] or "", "loan_amount": calculated_amount}),
            "property_address": property_address if request.include_property_address else None,
            "purchase_price": purchase_price,
            "approved_amount": calculated_amount,
            "expires_at": expiration_date,
            "partner_id": request.partner_id,
            "share_token": share_token
        })
        letter_id = result.fetchone()[0]
        db.commit()

        return {
            "success": True,
            "letter_id": letter_id,
            "letter_html": letter_html,
            "calculated_loan_amount": calculated_amount,
            "purchase_price": purchase_price,
            "property_address": property_address if request.include_property_address else None,
            "expires_at": expiration_date.isoformat(),
            "share_token": share_token,
            "share_url": f"/letters/shared/{share_token}"
        }

    except SQLAlchemyError as e:
        db.rollback()
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating pre-approval letter: {e}\n{error_details}")
        raise HTTPException(status_code=500, detail="Error")


@router.post("/preapproval/notify-overlimit")
async def notify_overlimit_request(
    request: NotifyOverLimitRequest,
    db: Session = Depends(get_db)
):
    """
    Notify loan officer about an over-limit pre-approval request.

    When a partner requests a pre-approval letter for a purchase price
    that exceeds the approved terms, this endpoint notifies the LO.
    """
    # Get lead and LO info
    lead = db.execute(text("""
        SELECT
            l.id, l.name, l.email, l.phone, l.owner_id
        FROM leads l
        WHERE l.id = :lead_id
    """), {"lead_id": request.lead_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get organization_id from the lead's owner
    owner_org_id = 1  # Default
    if lead[4]:  # owner_id
        owner = db.execute(text("SELECT organization_id FROM users WHERE id = :uid"), {"uid": lead[4]}).fetchone()
        if owner and owner[0]:
            owner_org_id = owner[0]

    # Get LO email
    lo_email = None
    lo_name = None
    if lead[4]:  # owner_id
        lo = db.execute(text("""
            SELECT full_name, email FROM users WHERE id = :user_id
        """), {"user_id": lead[4]}).fetchone()
        if lo:
            lo_name = lo[0]
            lo_email = lo[1]

    # Get partner info if provided
    partner_name = "A referral partner"
    if request.partner_id:
        partner = db.execute(text("""
            SELECT name, company FROM referral_partners WHERE id = :partner_id
        """), {"partner_id": request.partner_id}).fetchone()
        if partner:
            partner_name = f"{partner[0]} ({partner[1]})" if partner[1] else partner[0]

    # Send notification email
    if lo_email:
        try:
            notification_service = NotificationService()
            notification_service.send_email(
                to_email=lo_email,
                subject=f"Pre-Approval Request Exceeds Terms - {request.borrower_name or lead[1]}",
                html_content=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #d97706;">Pre-Approval Request Exceeds Terms</h2>
                    <p>{partner_name} has requested a pre-approval letter with terms that exceed the current approval:</p>

                    <div style="background: #fef3c7; border: 1px solid #fcd34d; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Borrower:</strong> {request.borrower_name or lead[1]}</p>
                        <p style="margin: 10px 0 0;"><strong>Requested Purchase Price:</strong> ${request.requested_purchase_price:,.0f}</p>
                        <p style="margin: 10px 0 0;"><strong>Current Max Approved:</strong> ${request.max_approved_amount:,.0f}</p>
                        <p style="margin: 10px 0 0;"><strong>Current Max Purchase Price:</strong> ${request.max_purchase_price:,.0f}</p>
                        <p style="margin: 10px 0 0; color: #dc2626;"><strong>Over by:</strong> ${request.requested_purchase_price - request.max_purchase_price:,.0f}</p>
                    </div>

                    <p>Please review the file and contact the partner to discuss options for increasing the approval amount.</p>

                    <p><a href="{os.getenv('FRONTEND_URL', 'https://perenniaai.com')}/leads/{request.lead_id}"
                          style="background: #1e40af; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        View Lead Details
                    </a></p>
                </div>
                """
            )
            logger.info(f"Sent over-limit notification to {lo_email} for lead {request.lead_id}")
        except Exception as e:
            logger.error(f"Failed to send over-limit notification: {e}")

    # Create a task for the LO
    try:
        db.execute(text("""
            INSERT INTO tasks (
                organization_id, lead_id, assigned_to, title, description,
                priority, status, created_at
            ) VALUES (
                :org_id, :lead_id, :assigned_to,
                'Pre-Approval Request Exceeds Terms',
                :description,
                'HIGH', 'pending', CURRENT_TIMESTAMP
            )
        """), {
            "org_id": owner_org_id,
            "lead_id": request.lead_id,
            "assigned_to": lead[4],  # owner_id
            "description": f"Partner {partner_name} requested pre-approval at ${request.requested_purchase_price:,.0f}, which exceeds the max ${request.max_purchase_price:,.0f}. Please review and contact partner."
        })
        db.commit()
    except SQLAlchemyError as e:
        logger.error(f"Failed to create task for over-limit request: {e}")
        db.rollback()

    return {
        "success": True,
        "message": "Loan officer has been notified",
        "lo_notified": lo_email is not None
    }


@router.post("/letters/{letter_id}/email")
async def email_letter(
    letter_id: int,
    db: Session = Depends(get_db)
):
    """
    Send a pre-approval letter via email.

    Sends the letter to the borrower and optionally to the requesting partner.
    """
    from services.realtor_letter_service import LetterGenerationService

    letter_service = LetterGenerationService(db)
    letter = letter_service.get_letter(letter_id)

    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")

    # Get lead/loan info for borrower email
    lead_info = db.execute(text("""
        SELECT name, email FROM leads WHERE id = :loan_id
    """), {"loan_id": letter["loan_id"]}).fetchone()

    if not lead_info or not lead_info[1]:
        raise HTTPException(status_code=400, detail="Borrower email not found")

    borrower_name = lead_info[0]
    borrower_email = lead_info[1]

    # Send email with letter
    try:
        notification_service = NotificationService()
        notification_service.send_email(
            to_email=borrower_email,
            subject=f"Your Pre-Approval Letter - {borrower_name}",
            html_content=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #1e40af;">Your Pre-Approval Letter</h2>
                <p>Dear {borrower_name},</p>
                <p>Please find your pre-approval letter attached below. This letter confirms your pre-approval status and can be shared with real estate agents and sellers.</p>

                <div style="background: #f0f9ff; border: 1px solid #bfdbfe; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Pre-Approved Amount:</strong> ${letter.get('approved_amount', 0):,.0f}</p>
                    {f"<p><strong>Property:</strong> {letter.get('property_address')}</p>" if letter.get('property_address') else ""}
                    <p><strong>Valid Until:</strong> {letter.get('expires_at', 'N/A')}</p>
                </div>

                <p>You can also access your letter online:</p>
                <p><a href="{os.getenv('FRONTEND_URL', 'https://perenniaai.com')}/letters/shared/{letter.get('share_token')}"
                      style="background: #1e40af; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Your Letter
                </a></p>

                <hr style="margin: 30px 0; border: none; border-top: 1px solid #e2e8f0;">
                {letter.get('html', '')}
            </div>
            """
        )
        logger.info(f"Sent pre-approval letter {letter_id} to {borrower_email}")

        return {
            "success": True,
            "message": "Letter sent successfully",
            "sent_to": borrower_email
        }

    except Exception as e:
        logger.error(f"Failed to send letter email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")


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

    # Send notification to loan officer
    try:
        # Get loan officer info and borrower name from the loan
        lo_info = db.execute(text("""
            SELECT
                u.email as lo_email,
                u.full_name as lo_name,
                l.borrower_name,
                l.loan_number
            FROM loans l
            JOIN users u ON u.id = l.owner_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if lo_info and lo_info.lo_email:
            # Get realtor name
            realtor_name = realtor.get("name") or realtor.get("company_name") or "A realtor partner"

            notification_service = NotificationService()
            notification_service.send_email(
                to_email=lo_info.lo_email,
                subject=f"New Message from Realtor - {lo_info.borrower_name or 'Loan'} ({lo_info.loan_number or loan_id})",
                html_content=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #1e40af;">New Realtor Portal Message</h2>
                    <p>You have received a new message from <strong>{realtor_name}</strong> regarding:</p>
                    <ul>
                        <li><strong>Borrower:</strong> {lo_info.borrower_name or 'N/A'}</li>
                        <li><strong>Loan #:</strong> {lo_info.loan_number or loan_id}</li>
                        {f'<li><strong>Callback Requested:</strong> Yes</li>' if request.request_callback else ''}
                    </ul>
                    <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; white-space: pre-wrap;">{request.message}</p>
                    </div>
                    <p><a href="{os.getenv('FRONTEND_URL', 'https://perenniaai.com')}/loans/{loan_id}"
                          style="background: #1e40af; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        View Loan Details
                    </a></p>
                </div>
                """
            )
            logger.info(f"Sent realtor message notification to {lo_info.lo_email} for loan {loan_id}")
    except Exception as notify_err:
        logger.error(f"Failed to send realtor message notification: {notify_err}")
        # Don't fail the message send just because notification failed

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
# PORTAL STATUS ENDPOINT
# =============================================================================

@router.get("/clients/{lead_id}/status")
async def get_client_portal_status(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """
    Check if a buyer's agent portal exists for a lead/loan.
    Used by the Portal Selector Modal to show Open/Build buttons.

    Returns:
        - has_portal: bool - whether a partner has access to this lead
        - portal_url: str - URL to access the portal (if exists)
        - partner_id: int - ID of the partner with access (if exists)
    """
    try:
        # Check if this lead has a referral partner assigned
        partner_access = db.execute(text("""
            SELECT
                rp.id as partner_id,
                rp.name,
                rp.email
            FROM referral_partners rp
            JOIN leads l ON l.referral_partner_id = rp.id
            WHERE l.id = :lead_id
            LIMIT 1
        """), {"lead_id": lead_id}).fetchone()

        if partner_access:
            return {
                "data": {
                    "has_portal": True,
                    "portal_url": f"/realtor-portal?lead_id={lead_id}",
                    "partner_id": partner_access[0],
                    "partner_name": partner_access[1] or "",
                    "partner_email": partner_access[2]
                }
            }
        else:
            return {
                "data": {
                    "has_portal": False,
                    "portal_url": None,
                    "partner_id": None
                }
            }
    except Exception as e:
        logger.error(f"Error checking portal status for lead {lead_id}: {e}")
        return {
            "data": {
                "has_portal": False,
                "portal_url": None,
                "partner_id": None,
                "error": "Internal server error"
            }
        }


# =============================================================================
# PARTNER NOTES ENDPOINT
# =============================================================================

@router.post("/clients/{client_id}/notes")
async def add_partner_note(
    client_id: int,
    request: PartnerNoteRequest,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    """
    Add a note from a partner to a client/lead.
    Sends email notifications to all team members associated with the lead.
    """
    # Get partner info - try partner token first, then check JWT
    partner_name = "Partner"
    partner_id = None

    if token:
        try:
            realtor = await get_current_realtor(token, db)
            partner_name = realtor.get("name") or realtor.get("company_name") or "Partner"
            partner_id = realtor.get("realtor_id")
        except Exception as e:
            logger.error(f"Error getting realtor info from token: {e}")

    # Get lead/client info (using owner_id which is the correct column name)
    try:
        lead_info = db.execute(text("""
            SELECT
                l.id,
                l.name as borrower_name,
                l.email as borrower_email,
                l.owner_id,
                u.email as lo_email,
                u.full_name as lo_name,
                u.organization_id
            FROM leads l
            LEFT JOIN users u ON u.id = l.owner_id
            WHERE l.id = :client_id
        """), {"client_id": client_id}).fetchone()
    except SQLAlchemyError as e:
        logger.error(f"Failed to query lead info: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Database error"}
        )

    if not lead_info:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Client not found"}
        )

    # Create activity record
    activity_id = None
    try:
        db.execute(text("""
            INSERT INTO activities (
                type, content, lead_id, user_id, created_at
            ) VALUES (
                'Note', :content, :lead_id, :user_id, CURRENT_TIMESTAMP
            )
        """), {
            "content": f"[Partner Note from {partner_name}] {request.content}",
            "lead_id": client_id,
            "user_id": lead_info.owner_id or 1
        })
        db.commit()

        # Get the activity ID (works for both SQLite and PostgreSQL)
        result = db.execute(text("""
            SELECT id FROM activities
            WHERE lead_id = :lead_id AND type = 'Note'
            ORDER BY created_at DESC LIMIT 1
        """), {"lead_id": client_id}).fetchone()
        activity_id = result[0] if result else None
    except SQLAlchemyError as e:
        logger.error(f"Failed to create activity: {e}")
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Failed to save note"}
        )

    # Get all team members to notify
    team_emails = []

    # Add assigned loan officer
    if lead_info.lo_email:
        team_emails.append({
            "email": lead_info.lo_email,
            "name": lead_info.lo_name or "Team Member"
        })

    # Get other team members from the organization
    try:
        if lead_info.organization_id:
            team_members = db.execute(text("""
                SELECT DISTINCT u.email, u.full_name
                FROM users u
                WHERE u.organization_id = :org_id
                    AND u.email IS NOT NULL
                    AND u.id != :owner_id
                LIMIT 10
            """), {
                "org_id": lead_info.organization_id,
                "owner_id": lead_info.owner_id or 0
            }).fetchall()

            for member in team_members:
                if member.email and member.email not in [t["email"] for t in team_emails]:
                    team_emails.append({
                        "email": member.email,
                        "name": member.full_name or "Team Member"
                    })
    except Exception as e:
        logger.error(f"Error fetching team members: {e}")

    # Send email notifications
    emails_sent = 0
    frontend_url = os.getenv('FRONTEND_URL', 'https://perenniaai.com')

    try:
        notification_service = NotificationService()

        for recipient in team_emails[:5]:  # Limit to 5 recipients
            try:
                notification_service.send_email(
                    to_email=recipient["email"],
                    subject=f"New Partner Note - {lead_info.borrower_name or 'Client'}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <div style="background: linear-gradient(135deg, #218D8D 0%, #14b8a6 100%); padding: 20px; border-radius: 8px 8px 0 0;">
                            <h2 style="color: white; margin: 0;">New Partner Note</h2>
                        </div>
                        <div style="padding: 20px; background: #f9fafb; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                            <p style="margin-top: 0;">Hi {recipient['name']},</p>
                            <p>You have a new note from <strong>{partner_name}</strong> regarding:</p>
                            <ul style="color: #374151;">
                                <li><strong>Client:</strong> {lead_info.borrower_name or 'N/A'}</li>
                            </ul>
                            <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #218D8D; margin: 20px 0;">
                                <p style="margin: 0; white-space: pre-wrap; color: #1f2937;">{request.content}</p>
                            </div>
                            <p style="margin-bottom: 20px;">Please review and respond to this note.</p>
                            <a href="{frontend_url}/leads/{client_id}"
                               style="background: #218D8D; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: 600;">
                                View Client & Respond
                            </a>
                            <p style="margin-top: 20px; font-size: 12px; color: #6b7280;">
                                This notification was sent from Perennia AI Partner Portal.
                            </p>
                        </div>
                    </div>
                    """
                )
                emails_sent += 1
                logger.info(f"Sent partner note notification to {recipient['email']}")
            except Exception as email_err:
                logger.error(f"Failed to send notification to {recipient['email']}: {email_err}")
    except Exception as notify_err:
        logger.error(f"Failed to initialize notification service: {notify_err}")

    return {
        "success": True,
        "activity_id": activity_id,
        "message": "Note added successfully",
        "notifications_sent": emails_sent
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
# COMPREHENSIVE CLIENT DETAIL ENDPOINT
# =============================================================================

@router.get("/clients/{loan_id}/full-details")
async def get_client_full_details(
    loan_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive client details for partner portal view.

    Returns all information a partner needs about a referred client:
    - Lead/loan information
    - Outstanding documents needed
    - Milestones with dates
    - Third-party orders (Appraisal, Title, Insurance)
    - Conversation history
    """
    realtor = await get_current_realtor(token, db)

    from services.realtor_permission_service import RealtorAccessValidator

    # Validate access
    validator = RealtorAccessValidator(db)
    access = validator.validate_access(realtor["realtor_id"], loan_id)
    if not access["valid"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    # Record view
    validator.record_view(realtor["realtor_id"], loan_id)

    # 1. Get loan/lead details
    loan = db.execute(text("""
        SELECT
            l.id, l.loan_number, l.stage as status, l.amount as loan_amount,
            l.loan_type, l.property_address, l.closing_date as expected_close_date,
            l.borrower_name, l.created_at, l.updated_at,
            l.interest_rate, l.loan_term, l.property_type,
            l.credit_score, l.dti_ratio, l.ltv_ratio,
            u.full_name as lo_name, u.email as lo_email, u.phone as lo_phone,
            l.property_city, l.property_state, l.property_zip
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Client not found")

    # 2. Get outstanding documents
    documents = db.execute(text("""
        SELECT
            sdr.id, sdr.doc_type, sdr.title, sdr.status, sdr.due_date,
            sdr.priority, sdr.created_at, sdr.upload_date,
            sdr.rejection_reason, sdr.applies_to
        FROM smart_document_requests sdr
        WHERE sdr.loan_id = :loan_id
        ORDER BY
            CASE sdr.status WHEN 'OPEN' THEN 0 WHEN 'PENDING_REVIEW' THEN 1 ELSE 2 END,
            sdr.priority DESC,
            sdr.due_date NULLS LAST
    """), {"loan_id": loan_id}).fetchall()

    outstanding_docs = []
    received_docs = []
    for doc in documents:
        doc_info = {
            "id": doc[0],
            "type": doc[1],
            "title": doc[2],
            "status": doc[3],
            "due_date": format_date(doc[4]),
            "priority": doc[5],
            "requested_date": format_date(doc[6]),
            "received_date": format_date(doc[7]),
            "rejection_reason": doc[8],
            "applies_to": doc[9]
        }
        if doc[3] in ['OPEN', 'REJECTED']:
            outstanding_docs.append(doc_info)
        else:
            received_docs.append(doc_info)

    # 3. Get milestones
    milestones = db.execute(text("""
        SELECT
            pm.id, pm.milestone_name, pm.is_completed, pm.completed_at,
            pm.target_date, pm.display_order, pm.status, pm.notes
        FROM portal_milestones pm
        WHERE pm.loan_id = :loan_id
        ORDER BY pm.display_order
    """), {"loan_id": loan_id}).fetchall()

    # 4. Get third-party orders (Appraisal, Title, Insurance)
    third_party_orders = db.execute(text("""
        SELECT
            tpo.id, tpo.order_type, tpo.vendor_name, tpo.status,
            tpo.ordered_at, tpo.due_date, tpo.received_at,
            tpo.amount, tpo.notes
        FROM third_party_orders tpo
        WHERE tpo.loan_id = :loan_id
        ORDER BY tpo.ordered_at DESC
    """), {"loan_id": loan_id}).fetchall()

    # Format third-party orders by type
    appraisal = None
    title = None
    insurance = None
    other_orders = []

    for order in third_party_orders:
        order_info = {
            "id": order[0],
            "type": order[1],
            "vendor": order[2],
            "status": order[3],
            "ordered_date": format_date(order[4]),
            "due_date": format_date(order[5]),
            "received_date": format_date(order[6]),
            "amount": float(order[7]) if order[7] else None,
            "notes": order[8]
        }
        if order[1] and 'appraisal' in order[1].lower():
            appraisal = order_info
        elif order[1] and 'title' in order[1].lower():
            title = order_info
        elif order[1] and 'insurance' in order[1].lower():
            insurance = order_info
        else:
            other_orders.append(order_info)

    # 5. Get conversation log
    conversations = db.execute(text("""
        SELECT
            pce.id, pce.event_type, pce.channel, pce.direction,
            pce.content, pce.created_at, pce.metadata
        FROM portal_communication_events pce
        WHERE pce.loan_id = :loan_id
        ORDER BY pce.created_at DESC
        LIMIT 50
    """), {"loan_id": loan_id}).fetchall()

    # 6. Get important dates
    important_dates = db.execute(text("""
        SELECT
            lid.id, lid.date_type, lid.date_value, lid.description,
            lid.is_completed, lid.completed_at
        FROM loan_important_dates lid
        WHERE lid.loan_id = :loan_id
        ORDER BY lid.date_value
    """), {"loan_id": loan_id}).fetchall()

    # Build response
    return {
        "success": True,
        "client": {
            "loan_id": loan[0],
            "loan_number": loan[1],
            "status": loan[2],
            "status_display": (loan[2] or "unknown").replace("_", " ").title(),
            "loan_amount": float(loan[3]) if loan[3] else None,
            "loan_type": loan[4],
            "interest_rate": float(loan[10]) if loan[10] else None,
            "loan_term": loan[11],
            "borrower_name": loan[7],
            "property": {
                "address": loan[5],
                "city": loan[18],
                "state": loan[19],
                "zip": loan[20],
                "type": loan[12]
            },
            "expected_close_date": format_date(loan[6]),
            "created_at": format_date(loan[8]),
            "updated_at": format_date(loan[9]),
            "financials": {
                "credit_score": loan[13],
                "dti_ratio": float(loan[14]) if loan[14] else None,
                "ltv_ratio": float(loan[15]) if loan[15] else None
            },
            "loan_officer": {
                "name": loan[16],
                "email": loan[17],
                "phone": loan[18] if len(loan) > 18 else None
            }
        },
        "documents": {
            "outstanding": outstanding_docs,
            "outstanding_count": len(outstanding_docs),
            "received": received_docs,
            "received_count": len(received_docs),
            "total": len(documents)
        },
        "milestones": [
            {
                "id": m[0],
                "name": m[1],
                "is_completed": m[2],
                "completed_at": format_date(m[3]),
                "target_date": format_date(m[4]),
                "order": m[5],
                "status": m[6],
                "notes": m[7]
            }
            for m in milestones
        ],
        "third_party_orders": {
            "appraisal": appraisal,
            "title": title,
            "homeowners_insurance": insurance,
            "other": other_orders
        },
        "conversation_log": [
            {
                "id": c[0],
                "type": c[1],
                "channel": c[2],
                "direction": c[3],
                "content": c[4],
                "created_at": format_date(c[5]),
                "metadata": c[6]
            }
            for c in conversations
        ],
        "important_dates": [
            {
                "id": d[0],
                "type": d[1],
                "date": format_date(d[2]),
                "description": d[3],
                "is_completed": d[4],
                "completed_at": format_date(d[5])
            }
            for d in important_dates
        ],
        "role": access["role"]
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
    Handle incoming SMS webhook (from Telnyx).

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

async def _realtor_ws_handler(websocket: WebSocket, token: str, db: Session):
    """
    Shared WebSocket handler for real-time loan updates.

    Security: Token sent as first message after connect (not in URL path)
    to avoid leaking session token into server/proxy access logs.
    Backwards compatible: old clients with /ws/{token} path still work.
    """
    import json as _json
    from services.realtor_crm_sync_service import realtor_sync_manager
    from services.realtor_permission_service import RealtorAccessValidator

    await websocket.accept()

    # If token not in path, wait for auth message
    if not token:
        import asyncio
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            msg = _json.loads(raw)
            if isinstance(msg, dict) and msg.get("type") == "auth":
                token = msg.get("token", "")
        except (asyncio.TimeoutError, Exception):
            await websocket.send_json({"type": "error", "message": "Authentication timeout"})
            await websocket.close(code=4001, reason="Authentication timeout")
            return

    if not token:
        await websocket.send_json({"type": "error", "message": "No token provided"})
        await websocket.close(code=4001, reason="No token provided")
        return

    # Validate token
    result = db.execute(text("""
        SELECT rs.realtor_id FROM realtor_sessions rs
        WHERE rs.token = :token AND rs.expires_at > CURRENT_TIMESTAMP
    """), {"token": token}).fetchone()

    if not result:
        await websocket.send_json({"type": "error", "message": "Invalid or expired session"})
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


@router.websocket("/ws/{token}")
async def realtor_websocket_compat(
    websocket: WebSocket,
    token: str,
    db: Session = Depends(get_db)
):
    """Backwards-compatible route: token in URL path (deprecated)."""
    await _realtor_ws_handler(websocket, token, db)


@router.websocket("/ws")
async def realtor_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """Secure route: token sent as first message after connect."""
    await _realtor_ws_handler(websocket, "", db)


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
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """
    Create a test realtor account for testing purposes.
    Requires admin API key for authorization.
    """
    import os
    import traceback
    expected_key = os.getenv("ADMIN_API_KEY", "")

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
                "profile": f"https://app.perenniaai.com/api/v1/realtor-portal/me?token={session_token}",
                "loans": f"https://app.perenniaai.com/api/v1/realtor-portal/loans?token={session_token}"
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
                # traceback logged server-side
            }
        )


@router.post("/admin/run-migration")
async def run_realtor_portal_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """
    Run the realtor portal migration to create all required tables.
    Requires admin API key for authorization.
    """
    import os
    import traceback
    expected_key = os.getenv("ADMIN_API_KEY", "")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = []

    # SQL commands to create tables (PostgreSQL)
    sql_commands = [
        # Enable extensions
        ("Enable pgcrypto", "CREATE EXTENSION IF NOT EXISTS pgcrypto;"),

        # Realtor portal users
        ("Create realtor_portal_users", """
            CREATE TABLE IF NOT EXISTS realtor_portal_users (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                first_name VARCHAR(255) NOT NULL,
                last_name VARCHAR(255) NOT NULL,
                password_hash VARCHAR(255),
                auth_provider VARCHAR(50) DEFAULT 'email',
                brokerage_name VARCHAR(255),
                license_number VARCHAR(100),
                license_state VARCHAR(10),
                primary_lo_id INTEGER,
                notification_preferences JSONB DEFAULT '{"email": true, "sms": true, "push": false}'::jsonb,
                timezone VARCHAR(100) DEFAULT 'America/New_York',
                is_active BOOLEAN DEFAULT TRUE,
                last_login_at TIMESTAMP WITH TIME ZONE,
                login_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Realtor portal sessions
        ("Create realtor_portal_sessions", """
            CREATE TABLE IF NOT EXISTS realtor_portal_sessions (
                id SERIAL PRIMARY KEY,
                realtor_id INTEGER NOT NULL REFERENCES realtor_portal_users(id) ON DELETE CASCADE,
                token VARCHAR(255) NOT NULL UNIQUE,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                ip_address VARCHAR(50),
                user_agent TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Sessions index
        ("Create sessions index", """
            CREATE INDEX IF NOT EXISTS idx_realtor_sessions_token ON realtor_portal_sessions(token);
        """),

        # Realtor loan associations
        ("Create realtor_loan_associations", """
            CREATE TABLE IF NOT EXISTS realtor_loan_associations (
                id SERIAL PRIMARY KEY,
                realtor_id INTEGER NOT NULL REFERENCES realtor_portal_users(id) ON DELETE CASCADE,
                loan_id INTEGER NOT NULL,
                role VARCHAR(50) DEFAULT 'buyer_agent',
                access_granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                granted_by_user_id INTEGER,
                access_revoked_at TIMESTAMP WITH TIME ZONE,
                last_viewed_at TIMESTAMP WITH TIME ZONE,
                view_count INTEGER DEFAULT 0,
                notify_status_changes BOOLEAN DEFAULT TRUE,
                notify_documents BOOLEAN DEFAULT TRUE,
                notify_messages BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_realtor_loan UNIQUE(realtor_id, loan_id)
            );
        """),

        # Portal status actions
        ("Create portal_status_actions", """
            CREATE TABLE IF NOT EXISTS portal_status_actions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_status VARCHAR(50) NOT NULL,
                can_view_status BOOLEAN DEFAULT TRUE,
                can_view_timeline BOOLEAN DEFAULT TRUE,
                can_view_documents BOOLEAN DEFAULT FALSE,
                can_download_documents BOOLEAN DEFAULT FALSE,
                can_upload_documents BOOLEAN DEFAULT FALSE,
                can_send_messages BOOLEAN DEFAULT TRUE,
                can_request_update BOOLEAN DEFAULT TRUE,
                can_generate_prequal BOOLEAN DEFAULT FALSE,
                can_generate_preapproval BOOLEAN DEFAULT FALSE,
                can_view_conditions BOOLEAN DEFAULT FALSE,
                can_schedule_meeting BOOLEAN DEFAULT TRUE,
                visible_document_types TEXT[] DEFAULT ARRAY[]::TEXT[],
                hidden_fields TEXT[] DEFAULT ARRAY[]::TEXT[],
                ai_assistant_enabled BOOLEAN DEFAULT TRUE,
                ai_allowed_topics TEXT[] DEFAULT ARRAY['status', 'timeline', 'general']::TEXT[],
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Letter templates
        ("Create letter_templates", """
            CREATE TABLE IF NOT EXISTS letter_templates (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                template_type VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                html_template TEXT NOT NULL,
                css_styles TEXT,
                header_html TEXT,
                footer_html TEXT,
                variables_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
                page_size VARCHAR(20) DEFAULT 'letter',
                margins JSONB DEFAULT '{"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"}'::jsonb,
                is_active BOOLEAN DEFAULT TRUE,
                is_default BOOLEAN DEFAULT FALSE,
                requires_nmls BOOLEAN DEFAULT TRUE,
                requires_signature BOOLEAN DEFAULT TRUE,
                expiration_days INTEGER DEFAULT 90,
                created_by INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Pre-approval letters (with lead_id for pre-approval stage)
        ("Create pre_approval_letters", """
            CREATE TABLE IF NOT EXISTS pre_approval_letters (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                lead_id INTEGER,
                loan_id INTEGER,
                template_id INTEGER,
                letter_type VARCHAR(50) NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                generated_html TEXT NOT NULL,
                generated_pdf_url TEXT,
                variables_used JSONB NOT NULL DEFAULT '{}'::jsonb,
                property_address TEXT,
                purchase_price DECIMAL(15,2),
                approved_amount DECIMAL(15,2) NOT NULL,
                down_payment_percent DECIMAL(5,2),
                loan_program VARCHAR(100),
                interest_rate DECIMAL(6,4),
                issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                is_void BOOLEAN DEFAULT FALSE,
                voided_at TIMESTAMP WITH TIME ZONE,
                voided_by INTEGER,
                void_reason TEXT,
                generated_by INTEGER,
                generated_by_realtor INTEGER,
                generation_method VARCHAR(50) DEFAULT 'manual',
                download_count INTEGER DEFAULT 0,
                last_downloaded_at TIMESTAMP WITH TIME ZONE,
                share_token VARCHAR(100) UNIQUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Add lead_id column if table exists but column doesn't
        ("Add lead_id to pre_approval_letters", """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pre_approval_letters')
                   AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'pre_approval_letters' AND column_name = 'lead_id') THEN
                    ALTER TABLE pre_approval_letters ADD COLUMN lead_id INTEGER;
                END IF;
            END $$;
        """),

        # Make loan_id nullable if it's required
        ("Make loan_id nullable in pre_approval_letters", """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'pre_approval_letters'
                           AND column_name = 'loan_id'
                           AND is_nullable = 'NO') THEN
                    ALTER TABLE pre_approval_letters ALTER COLUMN loan_id DROP NOT NULL;
                END IF;
            END $$;
        """),

        # Communication events
        ("Create portal_communication_events", """
            CREATE TABLE IF NOT EXISTS portal_communication_events (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                realtor_id INTEGER,
                loan_id INTEGER,
                user_id INTEGER,
                event_type VARCHAR(50) NOT NULL,
                channel VARCHAR(50) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                subject TEXT,
                content TEXT,
                content_html TEXT,
                attachments JSONB DEFAULT '[]'::jsonb,
                metadata JSONB DEFAULT '{}'::jsonb,
                status VARCHAR(50) DEFAULT 'sent',
                delivered_at TIMESTAMP WITH TIME ZONE,
                read_at TIMESTAMP WITH TIME ZONE,
                failed_at TIMESTAMP WITH TIME ZONE,
                failure_reason TEXT,
                ai_generated BOOLEAN DEFAULT FALSE,
                ai_model VARCHAR(100),
                ai_prompt_tokens INTEGER,
                ai_completion_tokens INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """),

        # Seed default status actions
        ("Seed default status actions", """
            INSERT INTO portal_status_actions (
                organization_id, loan_status,
                can_view_status, can_view_timeline, can_view_documents, can_download_documents,
                can_upload_documents, can_send_messages, can_request_update,
                can_generate_prequal, can_generate_preapproval, can_view_conditions,
                can_schedule_meeting, ai_assistant_enabled
            ) VALUES
            (NULL, 'lead', true, false, false, false, false, true, true, true, false, false, true, true),
            (NULL, 'application', true, true, false, false, false, true, true, true, false, false, true, true),
            (NULL, 'processing', true, true, true, true, true, true, true, false, true, false, true, true),
            (NULL, 'submitted', true, true, true, true, true, true, true, false, true, true, true, true),
            (NULL, 'underwriting', true, true, true, true, true, true, true, false, true, true, true, true),
            (NULL, 'conditional_approval', true, true, true, true, true, true, true, false, true, true, true, true),
            (NULL, 'clear_to_close', true, true, true, true, false, true, true, false, false, true, true, true),
            (NULL, 'funded', true, true, true, true, false, false, false, false, false, false, false, true),
            (NULL, 'denied', true, true, false, false, false, true, false, false, false, false, true, true),
            (NULL, 'withdrawn', true, true, false, false, false, false, false, false, false, false, false, false)
            ON CONFLICT DO NOTHING;
        """),
    ]

    try:
        for name, sql in sql_commands:
            try:
                logger.info(f"Running: {name}")
                db.execute(text(sql))
                db.commit()
                results.append({"step": name, "status": "success"})
            except SQLAlchemyError as e:
                error_msg = str(e)
                # Ignore "already exists" type errors
                if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                    results.append({"step": name, "status": "skipped", "reason": "already exists"})
                    db.rollback()
                else:
                    results.append({"step": name, "status": "error", "error": error_msg})
                    db.rollback()

        return {
            "success": True,
            "message": "Migration completed",
            "results": results,
            "successful": len([r for r in results if r["status"] == "success"]),
            "skipped": len([r for r in results if r["status"] == "skipped"]),
            "failed": len([r for r in results if r["status"] == "error"])
        }

    except SQLAlchemyError as e:
        db.rollback()
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        logger.error(f"Migration failed: {error_msg}\n{stack_trace}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_msg,
                "results": results,
                # traceback logged server-side
            }
        )


# =============================================================================
# ASSIGN PARTNER ENDPOINT
# =============================================================================

class AssignPartnerRequest(BaseModel):
    """Request to assign a referral partner to a client/lead."""
    partner_id: int = Field(..., description="The referral partner ID to assign")


@router.post("/clients/{client_id}/assign-partner")
async def assign_partner_to_client(
    client_id: int,
    request: AssignPartnerRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Assign a referral partner to a client/lead.
    This creates the Buyer's Agent Portal access for the partner.
    Requires CRM authentication.

    Args:
        client_id: The lead/client ID to assign the partner to
        request: Contains the partner_id to assign

    Returns:
        Success status with the assigned partner details
    """
    try:
        # Verify the lead exists
        lead = db.execute(text("""
            SELECT id, name, email, referral_partner_id
            FROM leads
            WHERE id = :client_id
        """), {"client_id": client_id}).fetchone()

        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead/client {client_id} not found")

        # Verify the partner exists
        partner = db.execute(text("""
            SELECT id, name, company, email
            FROM referral_partners
            WHERE id = :partner_id
        """), {"partner_id": request.partner_id}).fetchone()

        if not partner:
            raise HTTPException(status_code=404, detail=f"Referral partner {request.partner_id} not found")

        # Update the lead with the referral partner
        db.execute(text("""
            UPDATE leads
            SET referral_partner_id = :partner_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :client_id
        """), {"partner_id": request.partner_id, "client_id": client_id})

        db.commit()

        return {
            "success": True,
            "message": f"Partner {partner[1]} assigned to client",
            "data": {
                "client_id": client_id,
                "partner_id": partner[0],
                "partner_name": partner[1],
                "partner_company": partner[2],
                "portal_url": f"/partner-portal/{partner[0]}/client/{client_id}"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning partner to client {client_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
