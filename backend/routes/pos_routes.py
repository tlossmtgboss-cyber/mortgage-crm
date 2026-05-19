"""
Borrower-facing POS (Point-of-Sale) API routes for the Digital 1003.

Extends the existing routes in routes/pos/ with:
  - Document upload (POST /api/v1/pos/applications/{app_id}/documents)
  - Co-borrower invitation (POST /api/v1/pos/applications/{app_id}/coborrower/invite)
  - Application status (GET /api/v1/pos/applications/{app_id}/status)

The core CRUD routes (create, get, section upsert, submit) remain in
routes/pos/application.py. This module adds the supporting endpoints
and re-exports the existing routers for convenience.

Auth: All endpoints require a PURL token (borrower session token).
No LO auth is needed — the borrower authenticates via their portal link.

Usage:
    # In main.py or a registration module:
    from routes.pos_routes import router as pos_extra_router
    app.include_router(pos_extra_router)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    require_purl_token,
    require_purl_write_scope,
)

from database.models.pos import POSApplication, POSSectionKey
from routes.pos._helpers import (
    build_audit_context,
    get_application_service,
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)
from schemas.pos_schemas import (
    ApplicationStatusResponse,
    CoborrowerInviteRequest,
    CoborrowerInviteResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)
from services.pos.application_service import (
    ApplicationService,
    ApplicationStateError,
    AuditContext,
)
from services.pos_service import POSService

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["POS - Extended"],
)


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

def get_pos_service() -> POSService:
    return POSService()


# ---------------------------------------------------------------------------
# Document Upload
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a supporting document to the application",
)
async def upload_document(
    application_id: str,
    file: UploadFile = File(...),
    category: str = Form("other"),
    description: Optional[str] = Form(None),
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
    pos_service: POSService = Depends(get_pos_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> DocumentUploadResponse:
    """Upload a document (W-2, paystub, bank statement, etc.) to the application.

    The file is associated with the application's canonical BorrowerApplication
    record. Supported categories: income, assets, identity, property, credit, other.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a filename",
        )

    # SEC-002: MIME type allowlist — mortgage documents only.
    _ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/tiff",
        "image/heic",
        "image/heif",
    }
    _ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".heic", ".heif"}

    content_type = (file.content_type or "").lower().strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: PDF, JPEG, PNG, TIFF, HEIC.",
        )

    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file extension. Allowed: .pdf, .jpg, .jpeg, .png, .tiff, .heic.",
        )

    # Read the file content and compute size.
    content = await file.read()
    file_size = len(content)

    # Max file size: 25 MB.
    max_size = 25 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum size of 25 MB",
        )

    # Generate a unique filename with validated extension.
    storage_filename = f"{uuid.uuid4().hex}{ext}"

    try:
        doc = pos_service.upload_document(
            db,
            application=application,
            filename=storage_filename,
            original_filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            category=category,
            description=description,
            # TENANT-011: Prefix with org_id for multi-tenant S3 isolation
            storage_key=f"org_{application.organization_id}/pos/{application.id}/{storage_filename}",
            ctx=ctx,
        )
    except ApplicationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    db.commit()
    db.refresh(doc)

    return DocumentUploadResponse(
        id=doc.id,
        application_id=application.id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        category=doc.category.value if hasattr(doc.category, "value") else str(doc.category),
        description=doc.description,
        created_at=doc.created_at,
    )


@router.get(
    "/{application_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents attached to the application",
)
def list_documents(
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
    pos_service: POSService = Depends(get_pos_service),
) -> DocumentListResponse:
    """Return all documents uploaded to this application."""
    docs = pos_service.list_documents(db, application)

    return DocumentListResponse(
        application_id=application.id,
        documents=[
            DocumentUploadResponse(
                id=d.id,
                application_id=application.id,
                filename=d.filename,
                original_filename=d.original_filename,
                file_size=d.file_size,
                mime_type=d.mime_type,
                category=d.category.value if hasattr(d.category, "value") else str(d.category),
                description=d.description,
                created_at=d.created_at,
            )
            for d in docs
        ],
        total=len(docs),
    )


# ---------------------------------------------------------------------------
# Co-Borrower Invitation
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/coborrower/invite",
    response_model=CoborrowerInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a co-borrower to complete their portion of the application",
)
def invite_coborrower(
    body: CoborrowerInviteRequest,
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: Session = Depends(get_db),
    pos_service: POSService = Depends(get_pos_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> CoborrowerInviteResponse:
    """Generate a unique link for a co-borrower and optionally send an email.

    The co-borrower receives a tokenized link to fill in their personal info,
    employment, and declarations. Once complete, the application is marked as
    having co-borrower data.
    """
    try:
        invitation = pos_service.invite_coborrower(
            db,
            application=application,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
            relationship_type=body.relationship_type,
            ctx=ctx,
        )
    except ApplicationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    db.commit()
    db.refresh(invitation)

    # Build the invitation link.
    app_domain = os.getenv("APP_DOMAIN", "app.perenniaai.com")
    invitation_link = (
        f"https://{app_domain}/coborrower/{invitation.invitation_token}"
    )

    return CoborrowerInviteResponse(
        id=invitation.id,
        application_id=application.id,
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        status=invitation.status,
        invitation_link=invitation_link,
        sent_at=invitation.sent_at,
        expires_at=invitation.expires_at,
    )


# ---------------------------------------------------------------------------
# Application Status
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/status",
    response_model=ApplicationStatusResponse,
    summary="Get detailed application status with per-section breakdown",
)
def get_application_status(
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
    pos_service: POSService = Depends(get_pos_service),
) -> ApplicationStatusResponse:
    """Return the application's overall status, section-by-section completion,
    document count, and co-borrower invitation status.

    Use this endpoint for progress dashboards and resume-application flows.
    """
    status_data = pos_service.get_application_status(db, application)
    return ApplicationStatusResponse(**status_data)
