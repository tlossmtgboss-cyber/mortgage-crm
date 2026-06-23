"""
Builder Portal Routes
=====================
API endpoints for the CMG Builder Portal (static HTML on GitHub Pages).

Public endpoints (builder-facing, token-authenticated):
- POST /api/v1/builder-portal/register           Register + get submission token
- POST /api/v1/builder-portal/documents/upload    Initiate S3 presigned upload
- POST /api/v1/builder-portal/documents/confirm   Confirm S3 upload
- POST /api/v1/builder-portal/submit              Submit completed application

LO endpoints (JWT-authenticated):
- GET  /api/v1/builder-applications               List builder applications
- GET  /api/v1/builder-applications/{id}          View application detail
- GET  /api/v1/builder-applications/{id}/documents/{doc_id}/download  Download doc
- PATCH /api/v1/builder-applications/{id}/review  Approve/reject
"""

import logging
import os
import uuid
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Builder Portal"])

_register_rate_limits: Dict[str, List[float]] = defaultdict(list)
REGISTER_RATE_LIMIT = 5
REGISTER_RATE_WINDOW = 300


def _check_register_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    _register_rate_limits[ip] = [
        t for t in _register_rate_limits[ip] if now - t < REGISTER_RATE_WINDOW
    ]
    if len(_register_rate_limits[ip]) >= REGISTER_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    _register_rate_limits[ip].append(now)


# S3 config (shared with portal_document_routes)
S3_BUCKET = os.getenv('PERENNIA_DOCS_S3_BUCKET', 'perennia-documents')
MAX_FILE_SIZE = 25 * 1024 * 1024

ALLOWED_MIME_TYPES = {
    'application/pdf', 'image/jpeg', 'image/png', 'image/gif',
    'image/webp', 'image/heic',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'doc', 'docx'}

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        try:
            import boto3
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
            )
        except Exception as e:
            logger.warning(f"S3 client init failed: {e}")
    return _s3_client


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_builder_token(request: Request, db: Session) -> "BuilderApplication":
    """Validate builder submission token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing submission token")
    token = auth[7:]

    from database.models.builder_application import BuilderApplication
    app = db.query(BuilderApplication).filter(
        BuilderApplication.submission_token == token
    ).first()
    if not app:
        raise HTTPException(status_code=401, detail="Invalid submission token")

    if app.created_at and (datetime.now(timezone.utc) - app.created_at) > timedelta(days=30):
        raise HTTPException(status_code=401, detail="Submission token expired")

    return app


async def _get_current_user(request: Request, db: Session = Depends(get_db)):
    """Delegate to canonical auth (lazy import avoids circular deps)."""
    from auth.dependencies import get_current_user as _gcu
    return await _gcu(request, db)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    lo_slug: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(..., min_length=1, max_length=255)
    ein: Optional[str] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    phone: Optional[str] = None


class RegisterResponse(BaseModel):
    application_id: int
    submission_token: str
    lo_name: str
    lo_company: Optional[str] = None


class InitiateUploadRequest(BaseModel):
    doc_type: str = Field(..., min_length=1, max_length=100)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=MAX_FILE_SIZE)
    mime_type: str


class InitiateUploadResponse(BaseModel):
    document_id: int
    upload_url: str
    storage_key: str
    expires_in: int = 3600


class ConfirmUploadRequest(BaseModel):
    document_id: int
    etag: Optional[str] = None


class SubmitRequest(BaseModel):
    application_data: Dict[str, Any] = Field(default_factory=dict)
    signature_data: Dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    notes: Optional[str] = None


class BuilderDocumentOut(BaseModel):
    id: int
    doc_type: str
    file_name: str
    mime_type: str
    file_size: int
    status: str
    uploaded_at: Optional[str] = None

    class Config:
        from_attributes = True


class BuilderApplicationOut(BaseModel):
    id: int
    company_name: str
    ein: Optional[str] = None
    contact_first: str
    contact_last: str
    contact_email: str
    contact_phone: Optional[str] = None
    application_data: Dict[str, Any] = Field(default_factory=dict)
    signature_data: Dict[str, Any] = Field(default_factory=dict)
    status: str
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    submitted_at: Optional[str] = None
    created_at: Optional[str] = None
    documents: List[BuilderDocumentOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class BuilderApplicationSummary(BaseModel):
    id: int
    company_name: str
    contact_name: str
    contact_email: str
    status: str
    doc_count: int = 0
    submitted_at: Optional[str] = None
    created_at: Optional[str] = None


# ===========================================================================
# PUBLIC ENDPOINTS — builder-facing (no JWT, uses submission token)
# ===========================================================================

@router.post("/api/v1/builder-portal/register", response_model=RegisterResponse)
async def register_builder(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """
    Register a builder and create a draft application.
    Returns a submission token for subsequent API calls.
    """
    _check_register_rate_limit(request)

    from database.models.core import User
    from database.models.builder_application import BuilderApplication
    from database.models.referral import ReferralPartner

    # Resolve LO from slug
    lo = db.query(User).filter(
        User.slug == body.lo_slug,
        User.is_active == True,
    ).first()
    if not lo:
        raise HTTPException(status_code=404, detail="Loan officer not found")

    # Generate submission token
    token = f"bld_{secrets.token_urlsafe(48)}"

    # Create or find ReferralPartner
    partner = db.query(ReferralPartner).filter(
        ReferralPartner.organization_id == lo.organization_id,
        ReferralPartner.email == body.email,
        ReferralPartner.category == "Builder",
    ).first()

    if not partner:
        partner = ReferralPartner(
            organization_id=lo.organization_id,
            name=f"{body.first_name} {body.last_name}",
            company=body.company_name,
            business_name=body.company_name,
            contact_name=f"{body.first_name} {body.last_name}",
            category="Builder",
            type="Builder",
            email=body.email,
            phone=body.phone or "",
            status="active",
            owner_id=lo.id,
        )
        db.add(partner)
        db.flush()

    # Check for existing draft from same email for same LO
    existing = db.query(BuilderApplication).filter(
        BuilderApplication.contact_email == body.email,
        BuilderApplication.lo_user_id == lo.id,
        BuilderApplication.status == "DRAFT",
    ).first()

    if existing:
        return RegisterResponse(
            application_id=existing.id,
            submission_token=existing.submission_token,
            lo_name=f"{lo.first_name or ''} {lo.last_name or ''}".strip() or lo.email,
            lo_company=getattr(lo, 'company', None),
        )

    app = BuilderApplication(
        organization_id=lo.organization_id,
        lo_user_id=lo.id,
        partner_id=partner.id,
        submission_token=token,
        company_name=body.company_name,
        ein=body.ein,
        contact_first=body.first_name,
        contact_last=body.last_name,
        contact_email=body.email,
        contact_phone=body.phone,
        status="DRAFT",
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    logger.info(f"Builder application {app.id} created for LO {lo.id} ({lo.slug})")

    return RegisterResponse(
        application_id=app.id,
        submission_token=app.submission_token,
        lo_name=f"{lo.first_name or ''} {lo.last_name or ''}".strip() or lo.email,
        lo_company=getattr(lo, 'company', None),
    )


class ResumeRequest(BaseModel):
    lo_slug: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)


@router.post("/api/v1/builder-portal/resume", response_model=RegisterResponse)
async def resume_builder(body: ResumeRequest, request: Request, db: Session = Depends(get_db)):
    """Recover the submission token for an in-progress draft.

    The static Builder Portal stores the submission token in localStorage.
    If the builder loses that storage (cleared site data, switched browser,
    skipped past the register page on a deep link), every subsequent API
    call 401s and the review page shows
    "No submission token — please re-register."

    This endpoint lets the frontend silently re-acquire the token using the
    email + LO slug the builder already typed, without making the user
    re-fill the entire registration form. It only returns a token for an
    existing DRAFT application — submitted/approved/rejected packets are
    not resumable. Returns 404 (not 401/403) regardless of whether the
    email exists, to avoid leaking which builders have registered.
    """
    _check_register_rate_limit(request)

    from database.models.core import User
    from database.models.builder_application import BuilderApplication

    lo = db.query(User).filter(
        User.slug == body.lo_slug,
        User.is_active == True,
    ).first()
    if not lo:
        raise HTTPException(status_code=404, detail="No resumable application found")

    email_lower = body.email.strip().lower()
    existing = db.query(BuilderApplication).filter(
        BuilderApplication.contact_email.ilike(email_lower),
        BuilderApplication.lo_user_id == lo.id,
        BuilderApplication.status == "DRAFT",
    ).order_by(BuilderApplication.created_at.desc()).first()

    if not existing:
        raise HTTPException(status_code=404, detail="No resumable application found")

    if existing.created_at and (datetime.now(timezone.utc) - existing.created_at) > timedelta(days=30):
        raise HTTPException(status_code=404, detail="No resumable application found")

    logger.info(
        "Builder portal resume: app=%d lo=%d email=%s",
        existing.id, lo.id, email_lower,
    )

    return RegisterResponse(
        application_id=existing.id,
        submission_token=existing.submission_token,
        lo_name=f"{lo.first_name or ''} {lo.last_name or ''}".strip() or lo.email,
        lo_company=getattr(lo, 'company', None),
    )


@router.post("/api/v1/builder-portal/documents/upload", response_model=InitiateUploadResponse)
async def initiate_builder_upload(
    body: InitiateUploadRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get a presigned S3 URL for the builder to upload a document."""
    app = _require_builder_token(request, db)

    if body.mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")

    ext = body.file_name.rsplit('.', 1)[-1].lower() if '.' in body.file_name else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Extension '.{ext}' not allowed")

    from database.models.builder_application import BuilderDocument

    unique_id = uuid.uuid4().hex[:16]
    safe_name = "".join(c for c in body.file_name if c.isalnum() or c in '.-_').strip() or "document"
    storage_key = f"org/{app.organization_id}/builder-apps/{app.id}/{body.doc_type}/{unique_id}_{safe_name}"

    doc = BuilderDocument(
        application_id=app.id,
        organization_id=app.organization_id,
        doc_type=body.doc_type,
        file_name=body.file_name,
        mime_type=body.mime_type,
        file_size=body.file_size,
        storage_key=storage_key,
        status="PENDING_UPLOAD",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    s3 = _get_s3()
    if not s3:
        raise HTTPException(status_code=503, detail="Storage service unavailable")

    try:
        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': storage_key,
                'ContentType': body.mime_type,
            },
            ExpiresIn=3600,
        )
    except Exception as e:
        logger.error(f"Presigned URL generation failed: {e}")
        raise HTTPException(status_code=503, detail="Failed to generate upload URL")

    return InitiateUploadResponse(
        document_id=doc.id,
        upload_url=upload_url,
        storage_key=storage_key,
    )


@router.post("/api/v1/builder-portal/documents/confirm")
async def confirm_builder_upload(
    body: ConfirmUploadRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Confirm that a document was successfully uploaded to S3."""
    app = _require_builder_token(request, db)

    from database.models.builder_application import BuilderDocument
    doc = db.query(BuilderDocument).filter(
        BuilderDocument.id == body.document_id,
        BuilderDocument.application_id == app.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = "UPLOADED"
    doc.uploaded_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "confirmed", "document_id": doc.id}


@router.delete("/api/v1/builder-portal/documents/{doc_id}")
async def delete_builder_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a builder document (removes S3 object and DB record)."""
    app = _require_builder_token(request, db)

    from database.models.builder_application import BuilderDocument
    doc = db.query(BuilderDocument).filter(
        BuilderDocument.id == doc_id,
        BuilderDocument.application_id == app.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    s3 = _get_s3()
    if s3 and doc.storage_key:
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key=doc.storage_key)
        except Exception as e:
            logger.error(f"S3 delete failed for {doc.storage_key}: {e}")

    db.delete(doc)
    db.commit()

    return {"status": "deleted", "document_id": doc_id}


@router.post("/api/v1/builder-portal/submit")
async def submit_builder_application(
    body: SubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Final submission of the builder application.
    Stores form data + signature, marks SUBMITTED.
    """
    app = _require_builder_token(request, db)

    if app.status == "SUBMITTED":
        return {
            "status": "submitted",
            "application_id": app.id,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        }

    if app.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Cannot submit — status is {app.status}")

    app.application_data = body.application_data
    app.signature_data = body.signature_data
    app.status = "SUBMITTED"
    app.submitted_at = datetime.now(timezone.utc)
    app.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        from database.models.core import Notification
        notif = Notification(
            user_id=app.lo_user_id,
            organization_id=app.organization_id,
            type="builder_submission",
            title="Builder Application Submitted",
            message=f"{app.contact_first} {app.contact_last} ({app.company_name}) submitted their builder application",
            link=f"/referral-partners/{app.partner_id}",
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to create builder submission notification: {e}")

    logger.info(f"Builder application {app.id} submitted by {app.contact_email}")

    return {
        "status": "submitted",
        "application_id": app.id,
        "submitted_at": app.submitted_at.isoformat(),
    }


# ===========================================================================
# LO ENDPOINTS — JWT-authenticated
# ===========================================================================

@router.get("/api/v1/builder-applications", response_model=List[BuilderApplicationSummary])
async def list_builder_applications(
    request: Request,
    user=Depends(_get_current_user),
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    partner_id: Optional[int] = None,
):
    """List builder applications for the current LO's organization."""

    from database.models.builder_application import BuilderApplication, BuilderDocument
    from sqlalchemy import func

    query = db.query(
        BuilderApplication.id,
        BuilderApplication.company_name,
        BuilderApplication.contact_first,
        BuilderApplication.contact_last,
        BuilderApplication.contact_email,
        BuilderApplication.status,
        BuilderApplication.submitted_at,
        BuilderApplication.created_at,
        func.count(BuilderDocument.id).label("doc_count"),
    ).outerjoin(
        BuilderDocument, BuilderDocument.application_id == BuilderApplication.id
    ).filter(
        BuilderApplication.organization_id == user.organization_id,
    ).group_by(BuilderApplication.id)

    if status:
        query = query.filter(BuilderApplication.status == status.upper())

    if partner_id:
        query = query.filter(BuilderApplication.partner_id == partner_id)

    rows = query.order_by(BuilderApplication.created_at.desc()).all()

    return [
        BuilderApplicationSummary(
            id=r.id,
            company_name=r.company_name,
            contact_name=f"{r.contact_first} {r.contact_last}",
            contact_email=r.contact_email,
            status=r.status,
            doc_count=r.doc_count,
            submitted_at=r.submitted_at.isoformat() if r.submitted_at else None,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/api/v1/builder-applications/{app_id}")
async def get_builder_application(
    app_id: int,
    request: Request,
    user=Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Get full builder application detail (LO view)."""

    from database.models.builder_application import BuilderApplication
    app = db.query(BuilderApplication).filter(
        BuilderApplication.id == app_id,
        BuilderApplication.organization_id == user.organization_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    docs = []
    for d in app.documents:
        docs.append({
            "id": d.id,
            "doc_type": d.doc_type,
            "file_name": d.file_name,
            "mime_type": d.mime_type,
            "file_size": d.file_size,
            "status": d.status,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        })

    return {
        "id": app.id,
        "company_name": app.company_name,
        "ein": app.ein,
        "contact_first": app.contact_first,
        "contact_last": app.contact_last,
        "contact_email": app.contact_email,
        "contact_phone": app.contact_phone,
        "application_data": app.application_data or {},
        "signature_data": app.signature_data or {},
        "status": app.status,
        "review_notes": app.review_notes,
        "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "documents": docs,
    }


@router.get("/api/v1/builder-applications/{app_id}/documents/{doc_id}/download")
async def download_builder_document(
    app_id: int,
    doc_id: int,
    request: Request,
    user=Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a presigned download URL for a builder document."""

    from database.models.builder_application import BuilderApplication, BuilderDocument
    app = db.query(BuilderApplication).filter(
        BuilderApplication.id == app_id,
        BuilderApplication.organization_id == user.organization_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    doc = db.query(BuilderDocument).filter(
        BuilderDocument.id == doc_id,
        BuilderDocument.application_id == app_id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    s3 = _get_s3()
    if not s3:
        raise HTTPException(status_code=503, detail="Storage unavailable")

    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': doc.storage_key,
                'ResponseContentDisposition': f'attachment; filename="{doc.file_name}"',
            },
            ExpiresIn=300,
        )
    except Exception as e:
        logger.error(f"Download URL generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")

    return {"download_url": url, "file_name": doc.file_name, "expires_in": 300}


@router.patch("/api/v1/builder-applications/{app_id}/review")
async def review_builder_application(
    app_id: int,
    body: ReviewRequest,
    request: Request,
    user=Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Approve or reject a builder application."""

    from database.models.builder_application import BuilderApplication
    app = db.query(BuilderApplication).filter(
        BuilderApplication.id == app_id,
        BuilderApplication.organization_id == user.organization_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status not in ("SUBMITTED", "UNDER_REVIEW"):
        raise HTTPException(status_code=400, detail=f"Cannot review — status is {app.status}")

    new_status = "APPROVED" if body.action == "approve" else "REJECTED"
    app.status = new_status
    app.review_notes = body.notes
    app.reviewed_by = user.id
    app.reviewed_at = datetime.now(timezone.utc)
    app.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Builder application {app_id} {new_status} by user {user.id}")

    return {"status": new_status, "application_id": app_id}
