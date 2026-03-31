"""
Portal Smart Docs Routes

Borrower-facing API endpoints for Smart Docs integration in the client portal.
These endpoints allow borrowers to:
- View their document requirements (needs list)
- See document status and freshness
- Upload documents directly to fulfill requirements
"""

import logging
import re
import time
from collections import defaultdict
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.smart_docs_models import DocumentRequest, SmartDocument, RequestStatus, DocType
from models.purl import PURLWorkspace, PURLLoan
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal/smart-docs", tags=["Portal Smart Docs"])


# =============================================================================
# SECURITY CONSTANTS
# =============================================================================

# Minimum slug length — short slugs are trivially enumerable
MIN_SLUG_LENGTH = 8

# Per-IP rate limit window (seconds) and maximum requests within that window
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 30

# Allowed MIME types for borrower uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/gif",
}

# Filename characters that are never acceptable
_UNSAFE_FILENAME_RE = re.compile(r'[/\\:\*\?"<>\|\x00]')


# =============================================================================
# IN-MEMORY RATE LIMITER
# =============================================================================

# Structure: { ip: [(window_start, request_count), ...] }
# Each entry is a (window_start_epoch, count) pair for a 1-minute window.
_rate_limit_store: dict = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting common proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the leftmost (originating) IP
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check whether *ip* has exceeded the rate limit.

    Returns:
        (allowed: bool, remaining: int) — remaining requests left in window.
    """
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Purge expired windows for this IP
    _rate_limit_store[ip] = [
        (ts, cnt) for ts, cnt in _rate_limit_store[ip] if ts > window_start
    ]

    total_in_window = sum(cnt for _, cnt in _rate_limit_store[ip])

    if total_in_window >= RATE_LIMIT_MAX_REQUESTS:
        return False, 0

    # Record this request
    _rate_limit_store[ip].append((now, 1))
    remaining = RATE_LIMIT_MAX_REQUESTS - total_in_window - 1
    return True, max(0, remaining)


# =============================================================================
# PORTAL ACCESS VERIFICATION
# =============================================================================

def verify_portal_access(workspace_slug: str, request: Request, response: Response) -> None:
    """Enforce rate limiting and slug entropy on every portal request.

    Adds ``X-RateLimit-Remaining`` and ``X-Robots-Tag`` to *response*.

    Raises:
        HTTPException 400  — slug is too short / obviously guessable
        HTTPException 429  — caller has exceeded the per-IP rate limit
    """
    # Always prevent search-engine indexing of portal URLs
    response.headers["X-Robots-Tag"] = "noindex, nofollow"

    # Reject obviously guessable (too short) slugs immediately — no DB hit
    if len(workspace_slug) < MIN_SLUG_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace identifier.",
        )

    # Rate-limit by IP
    client_ip = _get_client_ip(request)
    allowed, remaining = _check_rate_limit(client_ip)
    response.headers["X-RateLimit-Remaining"] = str(remaining)

    if not allowed:
        logger.warning("Portal rate limit exceeded for IP %s (slug prefix: %s...)", client_ip, workspace_slug[:4])
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before trying again.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class DocumentRequirementResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    instructions: Optional[str]
    doc_type: str
    priority: str
    status: str
    required_count: int
    fulfilled_count: int
    freshness_days: Optional[int]
    due_date: Optional[str]
    is_overdue: bool
    documents: list

    class Config:
        from_attributes = True


class PortalNeedsListResponse(BaseModel):
    loan_id: int
    total_requirements: int
    completed_count: int
    pending_count: int
    overdue_count: int
    completion_percentage: int
    requirements: list


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_workspace_loan(db: Session, workspace_slug: str) -> tuple:
    """Get workspace and active loan from slug.

    Returns:
        tuple: (workspace, purl_loan, main_loan_id)
        - main_loan_id is the ID used in Smart Docs tables (references loans.id)
    """
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.slug == workspace_slug
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    loan = db.query(PURLLoan).filter(
        PURLLoan.workspace_id == workspace.id
    ).order_by(PURLLoan.created_at.desc()).first()

    if not loan:
        raise HTTPException(status_code=404, detail="No active loan found")

    # Smart Docs uses main_loan_id (references loans.id), not purl_loan.id
    main_loan_id = loan.main_loan_id or loan.id

    return workspace, loan, main_loan_id


def sanitize_filename(filename: str) -> str:
    """Remove path separators, null bytes, and other unsafe characters from a filename.

    Returns a safe, non-empty filename string.
    """
    if not filename:
        return "upload"
    # Strip path components
    basename = filename.replace("\\", "/").split("/")[-1]
    # Remove null bytes and unsafe shell/filesystem characters
    safe = _UNSAFE_FILENAME_RE.sub("_", basename)
    # Collapse runs of underscores/spaces and strip leading/trailing whitespace
    safe = re.sub(r"[_\s]{2,}", "_", safe).strip("_ ")
    return safe or "upload"


def format_requirement(request: DocumentRequest, documents: list) -> dict:
    """Format a document request for portal display."""
    now = datetime.utcnow()
    is_overdue = False
    if request.due_date and request.due_date < now and request.status == RequestStatus.OPEN:
        is_overdue = True

    # Count fulfilled documents for this request
    fulfilled_docs = [d for d in documents if d.request_id == request.id]

    return {
        "id": request.id,
        "title": request.title,
        "description": request.description,
        "instructions": request.instructions,
        "doc_type": request.doc_type.value if request.doc_type else "OTHER",
        "priority": request.priority.value if request.priority else "NORMAL",
        "status": request.status.value if request.status else "OPEN",
        "required_count": request.required_count or 1,
        "fulfilled_count": len(fulfilled_docs),
        "freshness_days": request.freshness_days,
        "due_date": request.due_date.isoformat() if request.due_date else None,
        "is_overdue": is_overdue,
        "documents": [
            {
                "id": doc.id,
                "filename": doc.file_name,
                "status": doc.status,
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
                "document_date": doc.doc_date.isoformat() if doc.doc_date else None,
                "is_expired": doc.is_expired,
            }
            for doc in fulfilled_docs
        ]
    }


# =============================================================================
# PORTAL ENDPOINTS
# =============================================================================

@router.get("/{workspace_slug}/requirements")
async def get_portal_requirements(
    workspace_slug: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Get document requirements for a borrower's loan.

    Returns the needs list with status, due dates, and uploaded documents.
    """
    verify_portal_access(workspace_slug, request, response)

    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Get all document requests for this loan (using main_loan_id for Smart Docs)
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == main_loan_id
    ).order_by(
        DocumentRequest.priority.desc(),
        DocumentRequest.due_date.asc().nullslast()
    ).all()

    # Get all documents for this loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == main_loan_id
    ).all()

    # Format requirements
    requirements = [format_requirement(req, documents) for req in requests]

    # Calculate stats
    completed = len([r for r in requirements if r["status"] in ["ACCEPTED", "WAIVED"]])
    pending = len([r for r in requirements if r["status"] in ["OPEN", "PENDING_REVIEW"]])
    overdue = len([r for r in requirements if r["is_overdue"]])

    total = len(requirements)
    completion_pct = int((completed / total) * 100) if total > 0 else 0

    return {
        "loan_id": main_loan_id,
        "workspace_slug": workspace_slug,
        "total_requirements": total,
        "completed_count": completed,
        "pending_count": pending,
        "overdue_count": overdue,
        "completion_percentage": completion_pct,
        "requirements": requirements
    }


@router.get("/{workspace_slug}/requirements/{request_id}")
async def get_requirement_detail(
    workspace_slug: str,
    request_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific document requirement."""
    verify_portal_access(workspace_slug, request, response)

    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    doc_request = db.query(DocumentRequest).filter(
        DocumentRequest.id == request_id,
        DocumentRequest.loan_id == main_loan_id
    ).first()

    if not doc_request:
        raise HTTPException(status_code=404, detail="Requirement not found")

    documents = db.query(SmartDocument).filter(
        SmartDocument.request_id == request_id,
        SmartDocument.loan_id == main_loan_id  # Belt-and-suspenders: confirm loan ownership
    ).all()

    return format_requirement(doc_request, documents)


@router.post("/{workspace_slug}/upload")
async def upload_document_for_requirement(
    workspace_slug: str,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    request_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload a document to fulfill a requirement.

    The document will be validated and linked to the specific requirement.
    """
    verify_portal_access(workspace_slug, request, response)

    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Validate MIME type against whitelist before reading the full file
    submitted_mime = file.content_type or ""
    if submitted_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{submitted_mime}'. "
                "Allowed types: PDF, JPEG, PNG, TIFF, GIF."
            ),
        )

    # Sanitize the uploaded filename
    safe_filename = sanitize_filename(file.filename or "")

    # Verify the request belongs to this loan (explicit ownership check)
    doc_request = db.query(DocumentRequest).filter(
        DocumentRequest.id == request_id,
        DocumentRequest.loan_id == main_loan_id
    ).first()

    if not doc_request:
        raise HTTPException(status_code=404, detail="Requirement not found")

    if doc_request.status in [RequestStatus.ACCEPTED, RequestStatus.WAIVED]:
        raise HTTPException(status_code=400, detail="This requirement has already been fulfilled")

    # Read file content
    content = await file.read()
    mime_type = submitted_mime
    file_size = len(content)

    # Validate file size (max 20MB)
    if file_size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # Use request.borrower_id if available, otherwise default to primary borrower
    borrower_id = doc_request.borrower_id if doc_request.borrower_id else 1
    if not doc_request.borrower_id:
        logger.info(f"Document request {request_id} has no borrower_id, defaulting to primary borrower (1)")

    # Get S3 service - must verify availability and upload BEFORE creating DB record
    s3_service = get_smart_docs_s3_service()

    # Check S3 availability
    if not s3_service.is_available:
        logger.error("S3 storage is not available - document upload will fail")
        raise HTTPException(
            status_code=503,
            detail="Document storage is temporarily unavailable. Please try again later."
        )

    # Generate storage key with org isolation (use sanitized filename)
    storage_key = s3_service.generate_storage_key(
        loan_id=main_loan_id,
        borrower_id=borrower_id,
        file_name=safe_filename,
        organization_id=getattr(workspace, 'organization_id', None),
    )

    # Upload file to S3 first
    upload_result = s3_service.upload_file(
        file_content=content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(main_loan_id),
            "borrower_id": str(borrower_id),
            "request_id": str(request_id),
            "original_filename": safe_filename
        }
    )

    if not upload_result.get("success"):
        logger.error(f"S3 upload failed: {upload_result.get('error')}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to store document: {upload_result.get('error', 'Unknown error')}"
        )

    # Only create document record AFTER successful S3 upload
    document = SmartDocument(
        request_id=request_id,
        loan_id=main_loan_id,
        borrower_id=borrower_id,
        file_name=safe_filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=storage_key,
        doc_type=doc_request.doc_type,
        status="UPLOADED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Process the document through the review pipeline (optional - don't fail upload if processing fails)
    result = None
    processing_error = None
    try:
        pipeline = DocumentReviewPipeline(db)
        result = pipeline.process_document(
            document_id=document.id,
            file_content=content,
            mime_type=mime_type,
            filename=safe_filename,
            doc_type=doc_request.doc_type,
            request_id=request_id,
        )

        # Update request status based on result
        if result.decision and result.decision.value == "ACCEPT":
            doc_request.status = RequestStatus.ACCEPTED
            doc_request.completed_at = datetime.utcnow()
            doc_request.fulfilled_at = datetime.utcnow()
        elif result.decision and result.decision.value == "REJECT":
            doc_request.status = RequestStatus.REJECTED
        elif doc_request.status == RequestStatus.OPEN:
            doc_request.status = RequestStatus.PENDING_REVIEW
        db.commit()

    except SQLAlchemyError as e:
        import traceback
        processing_error = str(e)
        logger.error(f"Error processing upload (non-fatal): {e}")
        logger.error(traceback.format_exc())
        # Still mark as pending review so document isn't lost
        if doc_request.status == RequestStatus.OPEN:
            doc_request.status = RequestStatus.PENDING_REVIEW
            db.commit()

    return {
        "success": True,
        "message": "Document uploaded successfully" + (" (processing pending)" if processing_error else ""),
        "document_id": document.id,
        "decision": result.decision.value if result and result.decision else None,
        "validation": {
            "is_screenshot": result.screenshot_result.get("is_screenshot") if result and result.screenshot_result else None,
            "is_fresh": result.freshness_result.get("is_fresh") if result and result.freshness_result else None,
            "rejection_reason": result.rejection_reason if result else None,
            "fix_instructions": result.fix_instructions if result else None,
        } if result else None,
        "requirement_status": doc_request.status.value,
        "processing_error": processing_error
    }


@router.get("/{workspace_slug}/summary")
async def get_document_summary(
    workspace_slug: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Get a summary of document collection progress for the portal dashboard.
    """
    verify_portal_access(workspace_slug, request, response)

    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Get request counts by status
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == main_loan_id
    ).all()

    by_status = {
        "open": 0,
        "pending_review": 0,
        "accepted": 0,
        "rejected": 0,
        "waived": 0
    }

    by_priority = {
        "critical": 0,
        "high": 0,
        "normal": 0,
        "low": 0
    }

    overdue_items = []

    now = datetime.utcnow()
    for req in requests:
        status_key = req.status.value.lower() if req.status else "open"
        if status_key in by_status:
            by_status[status_key] += 1

        priority_key = req.priority.value.lower() if req.priority else "normal"
        if priority_key in by_priority:
            by_priority[priority_key] += 1

        if req.due_date and req.due_date < now and req.status == RequestStatus.OPEN:
            overdue_items.append({
                "id": req.id,
                "title": req.title,
                "due_date": req.due_date.isoformat(),
                "days_overdue": (now - req.due_date).days
            })

    total = len(requests)
    completed = by_status["accepted"] + by_status["waived"]

    return {
        "loan_id": main_loan_id,
        "total_requirements": total,
        "completed": completed,
        "pending": by_status["open"] + by_status["pending_review"],
        "completion_percentage": int((completed / total) * 100) if total > 0 else 0,
        "by_status": by_status,
        "by_priority": by_priority,
        "overdue_items": overdue_items,
        "next_action": overdue_items[0]["title"] if overdue_items else (
            requests[0].title if requests and by_status["open"] > 0 else "All documents submitted!"
        )
    }
