"""
Smart Docs Portal V2 Routes

Enhanced borrower-facing document portal API (V2). Provides magic-link and
access-code authentication, document upload with auto-classification,
document checklist view, loan progress tracking, secure messaging,
e-signature integration, multi-language support, and portal analytics.

All endpoints are prefixed with /api/smart-docs/portal/v2 (the prefix is
applied by the registration module, so router paths start at /portal/v2).

Auth model:
- POST /portal/v2/auth/magic-link  -- public (rate-limited)
- POST /portal/v2/auth/verify      -- public (rate-limited)
- All other endpoints require a valid portal V2 JWT in X-Portal-Token header,
  Authorization: Bearer header, or ?token= query param.

Tenant isolation: Every authenticated endpoint cross-checks org_id from the
JWT against the loan's organization_id in the database.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from db import get_async_db
from services.smart_docs.borrower_portal_v2_service import (
    BorrowerPortalV2Service,
    PortalV2TokenService,
    PortalRateLimiter,
    get_borrower_portal_v2_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Smart Docs Portal V2"])


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class MagicLinkRequest(BaseModel):
    """Request to send a magic link to a borrower."""
    email: str = Field(..., description="Borrower email address")
    loan_id: int = Field(..., description="Loan ID to grant portal access for")
    org_id: int = Field(..., description="Organization ID")
    lang: str = Field(default="en", description="Language code (en, es)")


class VerifyAuthRequest(BaseModel):
    """Request to verify authentication via magic link token or access code."""
    email: Optional[str] = Field(default=None, description="Borrower email (required for access code)")
    token: Optional[str] = Field(default=None, description="JWT from magic link")
    access_code: Optional[str] = Field(default=None, description="6-digit access code from LO")


class SendMessageRequest(BaseModel):
    """Request to send a message from borrower to LO."""
    message: str = Field(..., min_length=1, max_length=5000, description="Message text")
    related_request_id: Optional[int] = Field(default=None, description="Related document request ID")


# =============================================================================
# Portal Token Verification Dependency
# =============================================================================

async def _get_portal_v2_user(request: Request) -> Dict:
    """
    FastAPI dependency: extract and verify portal V2 token.

    Checks for token in:
    1. X-Portal-Token header
    2. Authorization: Bearer header
    3. ?token= query parameter

    Returns:
        Dict with loan_id, borrower_email, org_id, scope.

    Raises:
        HTTPException(401): If no valid token found.
    """
    token = None

    # 1. X-Portal-Token header
    portal_header = request.headers.get("X-Portal-Token")
    if portal_header:
        token = portal_header.strip()

    # 2. Authorization: Bearer
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    # 3. Query parameter
    if not token:
        token = request.query_params.get("token")
        if token:
            token = token.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Portal authentication required. Please use your portal access link.",
        )

    try:
        claims = PortalV2TokenService.verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return claims


def _require_write_scope(portal_user: Dict) -> None:
    """Verify portal user has write scope."""
    if portal_user.get("scope") not in ("read_write", "write"):
        raise HTTPException(
            status_code=403,
            detail="This action requires write access. Please request a new portal link.",
        )


# =============================================================================
# 1. POST /portal/v2/auth/magic-link -- Send magic link
# =============================================================================

@router.post("/portal/v2/auth/magic-link")
async def send_magic_link(
    body: MagicLinkRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Send a magic link email to the borrower for portal access.

    The magic link contains a signed JWT with 24-hour expiry. The borrower
    clicks the link to authenticate and access their document portal.

    This endpoint is public but rate-limited to 5 requests per hour per email.

    Returns:
        Magic link URL, token, expiry, and email content for the caller to send.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.send_magic_link(
            borrower_email=body.email,
            loan_id=body.loan_id,
            org_id=body.org_id,
            lang=body.lang,
        )
        return {
            "success": True,
            "magic_link_url": result["magic_link_url"],
            "expires_at": result["expires_at"],
            "borrower_name": result["borrower_name"],
            "email_subject": result["email_subject"],
            "email_body": result["email_body"],
            "branding": result["branding"],
        }
    except ValueError as e:
        error_msg = str(e)
        if "Too many" in error_msg or "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except SQLAlchemyError as e:
        logger.exception(f"Database error in send_magic_link: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 2. POST /portal/v2/auth/verify -- Verify magic link or access code
# =============================================================================

@router.post("/portal/v2/auth/verify")
async def verify_auth(
    body: VerifyAuthRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Verify portal authentication via magic link token or 6-digit access code.

    Exactly one of `token` or `access_code` (with `email`) must be provided.

    On success, returns a session token that the client uses for all subsequent
    portal API calls (via X-Portal-Token header).

    Returns:
        Session token, borrower info, loan ID, and expiry.
    """
    if not body.token and not body.access_code:
        raise HTTPException(
            status_code=400,
            detail="Either token or access_code (with email) is required.",
        )

    if body.access_code and not body.email:
        raise HTTPException(
            status_code=400,
            detail="Email is required when using access code authentication.",
        )

    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.verify_auth(
            email=body.email,
            token=body.token,
            access_code=body.access_code,
        )

        # Log login event
        await svc._log_portal_event(
            loan_id=result["loan_id"],
            org_id=result["org_id"],
            event_type="portal_login",
            borrower_email=result["borrower_email"],
            metadata={"auth_method": result["auth_method"]},
        )

        return {
            "success": True,
            "session_token": result["session_token"],
            "borrower_email": result["borrower_email"],
            "loan_id": result["loan_id"],
            "org_id": result["org_id"],
            "scope": result["scope"],
            "expires_at": result["expires_at"],
            "auth_method": result["auth_method"],
        }
    except ValueError as e:
        error_msg = str(e)
        if "Too many" in error_msg or "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail=error_msg)
        if "expired" in error_msg.lower():
            raise HTTPException(status_code=401, detail=error_msg)
        raise HTTPException(status_code=401, detail=error_msg)
    except SQLAlchemyError as e:
        logger.exception(f"Database error in verify_auth: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 3. GET /portal/v2/checklist -- Get document checklist
# =============================================================================

@router.get("/portal/v2/checklist")
async def get_document_checklist(
    lang: str = Query(default="en", description="Language code (en, es)"),
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get the document checklist for the borrower's loan.

    Returns items grouped by category (Income, Assets, Identity, Property, etc.)
    with priority indicators, completion status, due dates, overdue warnings,
    and uploaded document details.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        checklist = await svc.get_checklist(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            lang=lang,
        )

        # Get branding for portal chrome
        branding = await svc._get_org_branding(portal_user["org_id"])

        return {
            "success": True,
            "checklist": checklist,
            "branding": branding,
            "borrower_email": portal_user["borrower_email"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_document_checklist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 4. POST /portal/v2/upload -- Upload document
# =============================================================================

@router.post("/portal/v2/upload")
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    request_id: Optional[int] = Form(default=None, description="Document request ID this fulfills"),
    doc_type: Optional[str] = Form(default=None, description="Document type hint"),
    upload_source: str = Form(default="WEB", description="Upload source: WEB, MOBILE"),
    camera_capture: bool = Form(default=False, description="Whether captured via mobile camera"),
    lang: str = Form(default="en", description="Language code"),
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upload a document to the borrower portal.

    Supports drag-and-drop and mobile camera capture. Files are validated
    for type/size, scanned, auto-classified via AI, and stored in S3.

    Accepted formats: PDF, JPG, PNG, TIFF, HEIC
    Maximum size: 25 MB

    Requires valid portal session token with write scope.
    """
    _require_write_scope(portal_user)

    # Read file content
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read upload file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.process_upload(
            file_bytes=file_bytes,
            filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            borrower_email=portal_user["borrower_email"],
            request_id=request_id,
            doc_type_hint=doc_type,
            upload_source=upload_source,
            camera_capture=camera_capture,
            lang=lang,
        )
        return {"success": True, **result}
    except ValueError as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except SQLAlchemyError as e:
        logger.exception(f"Database error in upload_document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 5. GET /portal/v2/progress -- Get loan progress
# =============================================================================

@router.get("/portal/v2/progress")
async def get_loan_progress(
    lang: str = Query(default="en", description="Language code (en, es)"),
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get loan progress for the borrower portal.

    Returns the visual pipeline stage indicator, estimated closing date,
    days to close, loan details, and a recent activity feed.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        progress = await svc.get_loan_progress(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            lang=lang,
        )

        # Get branding
        branding = await svc._get_org_branding(portal_user["org_id"])

        return {
            "success": True,
            "progress": progress,
            "branding": branding,
            "borrower_email": portal_user["borrower_email"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_loan_progress: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 6. GET /portal/v2/messages -- Get messages
# =============================================================================

@router.get("/portal/v2/messages")
async def get_messages(
    limit: int = Query(default=50, ge=1, le=100, description="Max messages to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get messages between the borrower and their loan officer.

    Returns messages in reverse chronological order with read receipts.
    Automatically marks unread LO messages as read when the borrower
    fetches them.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.get_messages(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            borrower_email=portal_user["borrower_email"],
            limit=limit,
            offset=offset,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 7. POST /portal/v2/messages -- Send message
# =============================================================================

@router.post("/portal/v2/messages")
async def send_message(
    body: SendMessageRequest,
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Send a message from the borrower to the loan officer.

    Messages can optionally reference a specific document request.
    File attachments should be uploaded separately via the upload endpoint.

    Requires valid portal session token with write scope.
    """
    _require_write_scope(portal_user)

    try:
        # Get borrower name from loan
        from sqlalchemy import text as sa_text
        loan_row = (await db.execute(
            sa_text("SELECT borrower_name FROM loans WHERE id = :id"),
            {"id": int(portal_user["loan_id"])},
        )).fetchone()
        borrower_name = loan_row[0] if loan_row else portal_user["borrower_email"]

        svc = get_borrower_portal_v2_service(db)
        result = await svc.send_message(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            borrower_email=portal_user["borrower_email"],
            borrower_name=borrower_name,
            message_text=body.message,
            related_request_id=body.related_request_id,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in send_message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 8. GET /portal/v2/signatures -- Get pending signatures
# =============================================================================

@router.get("/portal/v2/signatures")
async def get_pending_signatures(
    lang: str = Query(default="en", description="Language code (en, es)"),
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get pending e-signature documents for the borrower.

    Returns envelopes where the borrower is a recipient with a pending
    signature, including signing URLs, urgency indicators, and document details.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.get_pending_signatures(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
            borrower_email=portal_user["borrower_email"],
            lang=lang,
        )
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_pending_signatures: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 9. GET /portal/v2/branding -- Get portal branding (public-ish)
# =============================================================================

@router.get("/portal/v2/branding")
async def get_portal_branding(
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get white-label branding for the portal (org logo, colors, tagline).

    Used by the frontend to render the portal with organization-specific
    branding. Returns default Perennia branding if org has no custom config.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        branding = await svc._get_org_branding(portal_user["org_id"])
        return {"success": True, "branding": branding}
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_portal_branding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 10. GET /portal/v2/analytics -- Portal analytics (LO-facing, portal-token ok)
# =============================================================================

@router.get("/portal/v2/analytics")
async def get_portal_analytics(
    portal_user: Dict = Depends(_get_portal_v2_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get portal analytics for the loan (login frequency, upload patterns,
    completion rates).

    Useful for LOs to understand borrower engagement. Also accessible from
    the borrower portal to show their own activity summary.

    Requires valid portal session token.
    """
    try:
        svc = get_borrower_portal_v2_service(db)
        result = await svc.get_portal_analytics(
            loan_id=portal_user["loan_id"],
            org_id=portal_user["org_id"],
        )
        return {"success": True, "analytics": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.exception(f"Database error in get_portal_analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
