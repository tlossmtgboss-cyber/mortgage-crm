"""
Smart Docs CRUD Routes

Needs list management, document upload/download, merge, loan listing,
templates, events, freshness/expiration, payroll, queue, dashboard,
reminders, and health endpoints.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent, NeedsListTemplate,
    DocType, RequestStatus, RequestPriority, AppliesTo, PayrollFrequency,
    DocumentStatus,
)
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.auto_renewal_scheduler import AutoRenewalScheduler
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

from routes.smart_docs_models import (
    GenerateNeedsListRequest,
    SyncApplicationDocumentsRequest,
    UpdatePayrollFrequencyBody,
    MergeDocumentsRequest,
    ReminderSettingsBody,
    DOCUMENT_ID_TO_DOC_TYPE,
    FRESHNESS_DAYS,
    _get_loan_org_id,
    _verify_loan_tenant,
    _verify_document_tenant,
)

logger = logging.getLogger(__name__)


# =============================================================================
# File Upload Security Validation
# =============================================================================

# Allowed MIME types for document uploads
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/tiff',
    'image/gif',
    'image/bmp',
    'image/webp',
}

# Magic byte signatures for file type verification
MAGIC_BYTES = {
    b'%PDF': 'application/pdf',
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'II\x2a\x00': 'image/tiff',  # Little-endian TIFF
    b'MM\x00\x2a': 'image/tiff',  # Big-endian TIFF
    b'BM': 'image/bmp',
    b'RIFF': 'image/webp',  # WebP starts with RIFF
}


def validate_upload_file(file_content_type: str, file_bytes_header: bytes, filename: str) -> tuple:
    """Validate uploaded file. Returns (is_valid, error_message, sanitized_filename)."""
    # 1. Check MIME type against whitelist
    if file_content_type not in ALLOWED_MIME_TYPES:
        return False, f"File type '{file_content_type}' is not allowed. Accepted types: PDF, JPEG, PNG, TIFF, GIF", None

    # 2. Verify magic bytes match claimed MIME type
    detected_type = None
    for magic, mime in MAGIC_BYTES.items():
        if file_bytes_header[:len(magic)] == magic:
            detected_type = mime
            break

    if detected_type and detected_type != file_content_type:
        # Special case: some TIFF variants
        if not (detected_type.startswith('image/tiff') and file_content_type.startswith('image/tiff')):
            return False, "File content does not match declared file type", None

    # 3. Sanitize filename
    sanitized = sanitize_filename(filename)

    return True, None, sanitized


def sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filename."""
    if not filename:
        return "unnamed_document"
    # Remove path components
    filename = filename.replace('\\', '/').split('/')[-1]
    # Remove null bytes and control characters
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    # Replace potentially dangerous characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    # Ensure not empty after sanitization
    if not filename:
        return "unnamed_document"
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    return filename


def _safe_json_loads(value, default=None):
    """Safely parse a JSON string, returning a default on failure."""
    if not value:
        return default if default is not None else []
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


router = APIRouter(
    tags=["Smart Documents"],
)


# =============================================================================
# Needs List Endpoints
# =============================================================================

@router.post("/needs-list/generate")
async def generate_needs_list(
    request: GenerateNeedsListRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Generate a document needs list for a loan application.

    Based on the loan program, occupancy, and income type, generates
    appropriate document requirements using templates.
    """
    try:
        _verify_loan_tenant(db, request.loan_id, current_user)
        generator = NeedsListGenerator(db)
        result = generator.generate_needs_list(
            loan_id=request.loan_id,
            loan_program=request.loan_program,
            occupancy_type=request.occupancy_type,
            income_type=request.income_type,
            borrower_id=request.borrower_id,
            co_borrower_id=request.co_borrower_id,
            has_gift_funds=request.has_gift_funds,
            is_self_employed=request.is_self_employed,
            has_bankruptcy=request.has_bankruptcy,
            property_type=request.property_type,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate needs list: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/needs-list/{loan_id}")
async def get_needs_list(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get the current needs list for a loan with borrower info and document URLs."""
    from sqlalchemy import text

    _verify_loan_tenant(db, loan_id, current_user)

    # Get org_id for tenant validation in S3 operations
    org_id = getattr(current_user, 'organization_id', None)

    generator = NeedsListGenerator(db)
    result = generator.get_needs_list(loan_id)

    # Fetch borrower info from loans table (use engine to bypass RLS filtering)
    from db import engine as _engine
    with _engine.connect() as conn:
        loan_info = conn.execute(text("""
            SELECT borrower_name, borrower_email, loan_number, stage
            FROM loans WHERE id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

    if loan_info:
        result["borrower_name"] = loan_info.borrower_name
        result["borrower_email"] = loan_info.borrower_email
        result["loan_number"] = loan_info.loan_number
        result["stage"] = loan_info.stage
    else:
        # Fallback: try PURL system
        from models.purl import PURLLoan, PURLWorkspace, PURLContact
        purl_loan = db.query(PURLLoan).filter(PURLLoan.id == loan_id).first()
        if purl_loan and purl_loan.workspace_id:
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == purl_loan.workspace_id
            ).first()
            if workspace:
                result["borrower_name"] = workspace.display_name
                result["loan_number"] = purl_loan.loan_number
                result["stage"] = purl_loan.loan_purpose
                # Try to get email from contacts
                borrower_contact = db.query(PURLContact).filter(
                    PURLContact.workspace_id == purl_loan.workspace_id,
                    PURLContact.contact_type == 'borrower'
                ).first()
                if borrower_contact:
                    result["borrower_email"] = borrower_contact.email
                    if not result.get("borrower_name"):
                        result["borrower_name"] = f"{borrower_contact.first_name or ''} {borrower_contact.last_name or ''}".strip()

    # Get borrower_id from the first request that has one, for top-level response
    first_borrower_id = None
    for req in result.get("all_requests", []):
        if req.get("borrower_id"):
            first_borrower_id = req["borrower_id"]
            break
    result["borrower_id"] = first_borrower_id

    # Enrich each request with uploaded document info
    for req in result.get("all_requests", []):
        request_id = req.get("id")
        if request_id:
            # Get uploaded documents for this request (exclude deleted/superseded)
            uploaded_docs = db.query(SmartDocument).filter(
                SmartDocument.request_id == request_id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
            ).order_by(SmartDocument.created_at.desc()).all()

            if uploaded_docs:
                latest_doc = uploaded_docs[0]
                req["document_id"] = latest_doc.id
                req["filename"] = latest_doc.file_name
                req["uploaded_at"] = latest_doc.created_at.isoformat() if latest_doc.created_at else None

                # Generate presigned URL for viewing - verify file exists first
                if latest_doc.storage_key:
                    s3_service = get_smart_docs_s3_service()
                    if s3_service.is_available:
                        # Check if file actually exists in S3 before generating URL
                        if s3_service.file_exists(latest_doc.storage_key):
                            url_result = s3_service.get_presigned_download_url(
                                storage_key=latest_doc.storage_key,
                                file_name=latest_doc.file_name,
                                expires_in=3600,  # 1 hour
                                inline=True,  # Use inline disposition for iframe viewing
                                organization_id=org_id  # Pass org_id for tenant validation
                            )
                            if url_result.get("success"):
                                req["file_url"] = url_result["presigned_url"]
                                req["s3_url"] = url_result["presigned_url"]
                        else:
                            # File doesn't exist in S3 - mark as storage error
                            req["storage_error"] = True
                            req["storage_error_message"] = "Document file not found in storage. Please re-upload."
                            logger.warning(f"S3 file not found for document {latest_doc.id}: {latest_doc.storage_key}")

                req["document_id"] = latest_doc.id
                req["doc_date"] = latest_doc.doc_date.isoformat() if latest_doc.doc_date else None
                req["expiration_date"] = latest_doc.doc_expires_at.isoformat() if latest_doc.doc_expires_at else None

    return result


@router.post("/needs-list/sync-from-application")
async def sync_documents_from_application(
    request: SyncApplicationDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Sync document requirements from a mortgage application to Smart Docs.

    This endpoint receives the document requirements generated by the frontend
    application form and creates corresponding DocumentRequest records in the
    Smart Docs system. This allows borrowers to see and fulfill their document
    requirements in the client portal.
    """
    try:
        _verify_loan_tenant(db, request.loan_id, current_user)

        # Get organization_id for tenant isolation
        org_id = _get_loan_org_id(db, request.loan_id) or getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=400, detail="Cannot determine organization for this loan")

        created_requests = []
        skipped_count = 0

        # Check for existing requests to avoid duplicates
        existing_requests = db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == request.loan_id,
            DocumentRequest.is_active == True
        ).all()
        existing_titles = {r.title for r in existing_requests}

        for doc in request.documents:
            # Skip if already exists
            if doc.name in existing_titles:
                skipped_count += 1
                continue

            # Map frontend doc ID to DocType
            doc_type = DOCUMENT_ID_TO_DOC_TYPE.get(doc.id, DocType.OTHER)

            # Determine if this is a co-borrower document
            is_coborrower = doc.id.startswith('coborrower_')
            applies_to = AppliesTo.CO_BORROWER if is_coborrower else AppliesTo.BORROWER

            # Determine priority based on category
            if doc.category == 'identity':
                priority = RequestPriority.HIGH
            elif doc.category == 'income':
                priority = RequestPriority.HIGH
            else:
                priority = RequestPriority.NORMAL

            # Get freshness days for this doc type
            freshness_days = FRESHNESS_DAYS.get(doc_type)

            # Create the document request
            doc_request = DocumentRequest(
                organization_id=org_id,
                loan_id=request.loan_id,
                doc_type=doc_type,
                title=doc.name,
                description=doc.description,
                instructions=f"Please upload {doc.description}",
                priority=priority,
                applies_to=applies_to,
                freshness_days=freshness_days,
                status=RequestStatus.OPEN,
                is_active=True,
            )
            db.add(doc_request)
            created_requests.append({
                "id": doc.id,
                "title": doc.name,
                "doc_type": doc_type.value,
                "priority": priority.value,
            })

        # Log the sync event in same transaction
        if created_requests:
            event = DocPolicyEvent(
                loan_id=request.loan_id,
                event_type="NEEDS_LIST_GENERATED",
                payload={
                    "source": "application_sync",
                    "documents_synced": len(created_requests),
                    "skipped": skipped_count,
                    "borrower": request.borrower_first_name,
                    "co_borrower": request.co_borrower_first_name,
                }
            )
            db.add(event)

        db.commit()

        return {
            "success": True,
            "loan_id": request.loan_id,
            "created_count": len(created_requests),
            "skipped_count": skipped_count,
            "created_requests": created_requests,
            "message": f"Synced {len(created_requests)} document requirements"
        }

    except SQLAlchemyError as e:
        logger.exception(f"Failed to sync documents from application: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Document Upload & Processing
# =============================================================================

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    loan_id: int = Form(...),
    borrower_id: int = Form(...),
    request_id: Optional[int] = Form(None),
    doc_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Upload and process a document.

    Runs the full processing pipeline including:
    - Screenshot detection
    - Date extraction
    - Freshness validation
    - Accept/reject decision
    """
    _verify_loan_tenant(db, loan_id, current_user)
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Early size check using Content-Length header to reject before reading full body
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # Read magic bytes for type verification, then reset stream
    header = await file.read(8)
    await file.seek(0)

    # Validate MIME type, magic bytes, and sanitize filename
    claimed_content_type = file.content_type or "application/octet-stream"
    is_valid, validation_error, safe_filename = validate_upload_file(
        claimed_content_type, header, file.filename
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=validation_error)

    # Read file content
    file_content = await file.read()

    # Get file info
    mime_type = claimed_content_type
    file_size = len(file_content)

    # Validate file size (max 20MB) — belt-and-suspenders after early Content-Length check
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # Check storage quota (MTR-004)
    try:
        from services.storage_quota_service import check_storage_quota
        org_id_for_quota = _get_loan_org_id(db, loan_id)
        if org_id_for_quota:
            allowed, quota_details = check_storage_quota(db, org_id_for_quota, file_size)
            if not allowed:
                raise HTTPException(
                    status_code=413,
                    detail=quota_details.get("error", "Storage quota exceeded")
                )
    except HTTPException:
        raise
    except Exception as quota_err:
        logger.warning(f"Storage quota check skipped: {quota_err}")

    # Parse doc_type
    parsed_doc_type = None
    if doc_type:
        try:
            parsed_doc_type = DocType(doc_type)
        except ValueError:
            logger.warning(f"Invalid doc_type: {doc_type}")

    # Get S3 service
    s3_service = get_smart_docs_s3_service()

    # Generate storage key with org isolation
    org_id = _get_loan_org_id(db, loan_id)
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=safe_filename,
        organization_id=org_id,
    )

    # Validate request_id FK before proceeding
    if request_id:
        request_exists = db.query(DocumentRequest.id).filter(
            DocumentRequest.id == request_id,
            DocumentRequest.loan_id == loan_id
        ).first()
        if not request_exists:
            raise HTTPException(status_code=400, detail="Invalid request_id")

    # Check for a prior UPLOAD_FAILED document for the same request so we can
    # recover instead of leaving orphaned records (SD-STATE-003).
    document = None
    if request_id:
        document = db.query(SmartDocument).filter(
            SmartDocument.request_id == request_id,
            SmartDocument.loan_id == loan_id,
            SmartDocument.borrower_id == borrower_id,
            SmartDocument.status == DocumentStatus.UPLOAD_FAILED.value,
        ).first()

    if document:
        # Re-use the failed record: update it with the new upload details
        document.file_name = safe_filename
        document.mime_type = mime_type
        document.file_size = file_size
        document.storage_key = storage_key
        document.doc_type = parsed_doc_type
        document.status = DocumentStatus.UPLOADED.value
        document.uploaded_at = datetime.now(timezone.utc)
        logger.info(
            "Recovering UPLOAD_FAILED document %d for request %d",
            document.id, request_id,
        )
    else:
        # Create new document record
        document = SmartDocument(
            organization_id=org_id,
            request_id=request_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            file_name=safe_filename,
            mime_type=mime_type,
            file_size=file_size,
            storage_key=storage_key,
            doc_type=parsed_doc_type,
            status=DocumentStatus.UPLOADED.value,
        )
        db.add(document)

    db.flush()  # Get the ID without committing

    # Upload file to S3
    upload_result = s3_service.upload_file(
        file_content=file_content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(loan_id),
            "borrower_id": str(borrower_id),
            "document_id": str(document.id),
            "original_filename": safe_filename
        }
    )

    if not upload_result.get("success"):
        logger.error(f"S3 upload failed for document {document.id}: {upload_result.get('error')}")
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Document storage temporarily unavailable"
        )

    # Only commit after S3 succeeds
    db.commit()
    db.refresh(document)

    # Record storage usage for quota tracking (MTR-004)
    try:
        from services.storage_quota_service import record_storage_usage
        record_storage_usage(db, org_id, storage_key, file_size, file_type=parsed_doc_type.value if parsed_doc_type else "document")
    except Exception as track_err:
        logger.warning(f"Storage usage tracking skipped: {track_err}")

    # Process the document
    pipeline = DocumentReviewPipeline(db)
    result = pipeline.process_document(
        document_id=document.id,
        file_content=file_content,
        mime_type=mime_type,
        filename=safe_filename,
        doc_type=parsed_doc_type,
        request_id=request_id,
    )

    response = pipeline.result_to_dict(result)
    response["storage_key"] = storage_key
    response["filename"] = safe_filename
    return response


@router.get("/document/{document_id}")
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get document details and processing results."""
    # Tenant isolation: verify document exists and belongs to user's organization
    document = _verify_document_tenant(db, document_id, current_user)

    return {
        "id": document.id,
        "loan_id": document.loan_id,
        "borrower_id": document.borrower_id,
        "request_id": document.request_id,
        "file_name": document.file_name,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "doc_type": document.doc_type.value if document.doc_type else None,
        "detected_doc_type": document.detected_doc_type,
        "status": document.status,
        "decision": document.decision.value if document.decision else None,
        "rejection_category": document.rejection_category.value if document.rejection_category else None,
        "rejection_reason": document.rejection_reason,
        "fix_instructions": document.fix_instructions,
        "screenshot_detection": {
            "is_screenshot": document.detected_is_screenshot,
            "confidence": document.screenshot_confidence,
            "reasons": document.screenshot_reasons,
        },
        "dates": {
            "doc_date": document.doc_date.isoformat() if document.doc_date else None,
            "extracted_dates": document.extracted_dates,
            "expires_at": document.doc_expires_at.isoformat() if document.doc_expires_at else None,
            "is_expired": document.is_expired,
            "days_until_expiration": document.days_until_expiration,
        },
        "extraction_confidence": document.extraction_confidence,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "reviewed_by": document.reviewed_by,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.get("/document/{document_id}/download")
async def download_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get a presigned URL to download a document.

    Returns a temporary URL that can be used to download the file directly from S3.
    Requires authentication and verifies the requesting user's org matches the document's loan org.
    """
    # Tenant isolation: verify document exists and belongs to user's organization
    document = _verify_document_tenant(db, document_id, current_user)
    org_id = getattr(current_user, 'organization_id', None)

    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document file not available")

    s3_service = get_smart_docs_s3_service()

    if not s3_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Document storage not configured"
        )

    result = s3_service.get_presigned_download_url(
        storage_key=document.storage_key,
        file_name=document.file_name,
        expires_in=300,  # 5 minutes
        organization_id=org_id  # Pass org_id for tenant validation
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {result.get('error')}"
        )

    try:
        from utils.export_audit import log_export_event, _get_client_ip
        log_export_event(
            db=db, user_id=getattr(current_user, "id", 0),
            organization_id=org_id, resource_type="document",
            export_format=document.mime_type or "binary",
            ip_address=_get_client_ip(request),
            details={"document_id": document_id, "file_name": document.file_name},
        )
    except Exception as e:
        logger.warning("Failed to log export event for document %s: %s", document_id, e)

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "download_url": result["presigned_url"],
        "expires_in": result["expires_in"],
        "content_type": document.mime_type,
        "file_size": document.file_size
    }


@router.post("/document/{document_id}/email")
async def email_single_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Email a single document to the loan's borrower or LO."""
    document = _verify_document_tenant(db, document_id, current_user)

    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document file not available")

    from database.models.lead_loan import Loan
    loan = db.query(Loan).filter(Loan.id == document.loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    recipient_email = getattr(current_user, 'email', None)
    if not recipient_email:
        raise HTTPException(status_code=400, detail="No recipient email available")

    s3_service = get_smart_docs_s3_service()
    if not s3_service.is_available:
        raise HTTPException(status_code=503, detail="Document storage not configured")

    download_result = s3_service.download_file(document.storage_key)
    if not download_result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to download document from storage")
    file_bytes = download_result["content"]

    try:
        from email_service import EmailService
        email_service = EmailService()
        filename = document.file_name or f"{document.doc_type}.pdf"
        email_service.send_email(
            to=recipient_email,
            subject=f"Document: {filename} - {getattr(loan, 'borrower_name', '') or 'Loan ' + str(loan.id)}",
            body=f"<p>Please find the attached document for loan {getattr(loan, 'loan_number', '') or loan.id}.</p><p>This is an automated message from Perennia AI.</p>",
            attachments=[{
                "filename": filename,
                "content": file_bytes,
                "content_type": document.mime_type or "application/pdf"
            }]
        )
        return {"success": True, "message": f"Document sent to {recipient_email}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to email document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")


@router.post("/merge")
async def merge_documents(
    request: MergeDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Merge multiple documents into a single PDF for download.

    Downloads specified documents from S3, merges them into a single PDF,
    and returns the merged file.
    """
    from fastapi.responses import StreamingResponse
    from pypdf import PdfWriter, PdfReader
    from database.models.lead_loan import Loan
    import io

    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    # Tenant isolation - verify loan belongs to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    loan_query = db.query(Loan).filter(Loan.id == request.loan_id)
    if not is_platform_admin and org_id:
        loan_query = loan_query.filter(Loan.organization_id == org_id)

    loan = loan_query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all requested documents
    documents = db.query(SmartDocument).filter(
        SmartDocument.id.in_(request.document_ids),
        SmartDocument.loan_id == request.loan_id
    ).all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found")

    if len(documents) != len(request.document_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Some documents not found. Requested {len(request.document_ids)}, found {len(documents)}"
        )

    s3_service = get_smart_docs_s3_service()
    if not s3_service.is_available:
        raise HTTPException(status_code=503, detail="Document storage not available")

    # Download and merge PDFs using PdfWriter (pypdf 4.x)
    writer = PdfWriter()
    merged_any = False
    errors = []

    for doc in documents:
        if not doc.storage_key:
            errors.append(f"{doc.file_name}: No storage key")
            continue

        try:
            # Download file from S3
            download_result = s3_service.download_file(doc.storage_key)
            if not download_result.get("success"):
                errors.append(f"{doc.file_name}: {download_result.get('error', 'Failed to download')}")
                continue

            file_data = download_result["content"]

            # Check if it's a PDF
            if doc.mime_type == "application/pdf" or doc.file_name.lower().endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(file_data))
                for page in pdf_reader.pages:
                    writer.add_page(page)
                merged_any = True
            else:
                # For non-PDF files, skip with warning
                errors.append(f"{doc.file_name}: Not a PDF, skipping")
        except Exception as e:
            logger.error(f"Error processing document {doc.id}: {e}")
            errors.append(f"{doc.file_name}: processing failed")

    if not merged_any:
        raise HTTPException(
            status_code=400,
            detail=f"No PDF documents could be merged. Errors: {', '.join(errors)}"
        )

    # Write merged PDF to bytes
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    # Use already-retrieved loan for filename
    filename = f"merged_documents_{loan.borrower_name if loan.borrower_name else request.loan_id}.pdf"

    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/merge-email")
async def merge_and_email_documents(
    request: MergeDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Merge multiple documents into a single PDF and email it.

    Downloads specified documents from S3, merges them into a single PDF,
    and sends via email.
    """
    from pypdf import PdfWriter, PdfReader
    from database.models.lead_loan import Loan
    import io

    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    # Tenant isolation - verify loan belongs to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    loan_query = db.query(Loan).filter(Loan.id == request.loan_id)
    if not is_platform_admin and org_id:
        loan_query = loan_query.filter(Loan.organization_id == org_id)

    loan = loan_query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all requested documents
    documents = db.query(SmartDocument).filter(
        SmartDocument.id.in_(request.document_ids),
        SmartDocument.loan_id == request.loan_id
    ).all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found")

    s3_service = get_smart_docs_s3_service()
    if not s3_service.is_available:
        raise HTTPException(status_code=503, detail="Document storage not available")

    # Determine recipient email
    import re
    recipient_email = request.recipient_email
    if not recipient_email:
        if loan.loan_officer_email:
            recipient_email = loan.loan_officer_email
        elif hasattr(loan, 'borrower_email') and loan.borrower_email:
            recipient_email = loan.borrower_email
        else:
            raise HTTPException(status_code=400, detail="No recipient email provided or available")

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', recipient_email):
        raise HTTPException(status_code=400, detail="Invalid recipient email address")

    # Download and merge PDFs using PdfWriter (pypdf 4.x)
    writer = PdfWriter()
    merged_any = False
    doc_names = []

    for doc in documents:
        if not doc.storage_key:
            continue

        try:
            download_result = s3_service.download_file(doc.storage_key)
            if not download_result.get("success"):
                logger.warning(f"Failed to download {doc.file_name}: {download_result.get('error')}")
                continue

            file_data = download_result["content"]

            if doc.mime_type == "application/pdf" or doc.file_name.lower().endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(file_data))
                for page in pdf_reader.pages:
                    writer.add_page(page)
                merged_any = True
                doc_names.append(doc.file_name)
        except Exception as e:
            logger.error(f"Error processing document {doc.id} for email: {e}")

    if not merged_any:
        raise HTTPException(status_code=400, detail="No PDF documents could be merged")

    # Write merged PDF to bytes
    output = io.BytesIO()
    writer.write(output)
    pdf_bytes = output.getvalue()

    # Send email with attachment
    try:
        from email_service import EmailService
        email_service = EmailService()

        filename = f"merged_documents_{loan.borrower_name or loan.id}.pdf"

        email_service.send_email(
            to=recipient_email,
            subject=f"Merged Documents - {loan.borrower_name or 'Loan ' + str(loan.id)}",
            body=f"""
            <p>Please find attached the merged documents for loan {loan.loan_number or loan.id}.</p>
            <p>Documents included:</p>
            <ul>
                {''.join(f'<li>{name}</li>' for name in doc_names)}
            </ul>
            <p>This is an automated message from Perennia AI.</p>
            """,
            attachments=[{
                "filename": filename,
                "content": pdf_bytes,
                "content_type": "application/pdf"
            }]
        )

        return {
            "success": True,
            "message": f"Merged {len(doc_names)} documents and sent to {recipient_email}",
            "documents_merged": doc_names,
            "recipient": recipient_email
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send merged documents email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")


@router.get("/documents/{loan_id}")
async def get_loan_documents(
    loan_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all documents for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    query = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id
    )

    if status:
        query = query.filter(SmartDocument.status == status)

    documents = query.order_by(SmartDocument.created_at.desc()).all()

    return {
        "loan_id": loan_id,
        "total": len(documents),
        "documents": [
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "status": doc.status,
                "decision": doc.decision.value if doc.decision else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
    }


# Alias route for backward compatibility
@router.get("/loan/{loan_id}/documents")
async def get_loan_documents_alias(
    loan_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Alias for /documents/{loan_id} - backward compatibility."""
    return await get_loan_documents(loan_id, status, db, current_user)


# =============================================================================
# Freshness & Expiration
# =============================================================================

@router.get("/expiring")
async def get_expiring_documents(
    loan_id: Optional[int] = None,
    days_ahead: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get documents expiring within the specified window."""
    if loan_id:
        _verify_loan_tenant(db, loan_id, current_user)

    scheduler = AutoRenewalScheduler(db)
    expiring = scheduler.get_upcoming_expirations(
        loan_id=loan_id,
        days_ahead=days_ahead,
    )

    # Tenant isolation: when no loan_id filter, restrict results to user's org
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not loan_id and org_id and not is_platform_admin:
        from sqlalchemy import text as sa_text
        tenant_loan_ids = {
            row[0] for row in db.execute(
                sa_text("SELECT id FROM loans WHERE organization_id = :org_id"),
                {"org_id": org_id}
            ).fetchall()
        }
        expiring = [doc for doc in expiring if doc.get("loan_id") in tenant_loan_ids]

    return {
        "days_ahead": days_ahead,
        "expiring_documents": expiring,
    }


@router.post("/check-expiration")
async def run_expiration_check(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Run expiration check and mark expired documents. Requires admin."""
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    scheduler = AutoRenewalScheduler(db)
    return scheduler.run_expiration_check()


@router.post("/process-renewals")
async def process_renewals(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Process pending document renewals. Requires admin."""
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if not is_platform_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    scheduler = AutoRenewalScheduler(db)
    return scheduler.process_pending_renewals()


# =============================================================================
# Payroll Frequency
# =============================================================================

@router.post("/infer-payroll-frequency/{borrower_id}")
async def infer_payroll_frequency(
    borrower_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Infer payroll frequency from historical paystub data."""
    # Tenant isolation: verify borrower belongs to a loan owned by user's org
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if org_id and not is_platform_admin:
        from sqlalchemy import text as sa_text
        borrower_loan = db.execute(
            sa_text("""
                SELECT l.id FROM loans l
                JOIN smart_documents sd ON sd.loan_id = l.id
                WHERE sd.borrower_id = :borrower_id AND l.organization_id = :org_id
                LIMIT 1
            """),
            {"borrower_id": borrower_id, "org_id": org_id}
        ).first()
        if not borrower_loan:
            raise HTTPException(status_code=404, detail="Not found")

    scheduler = AutoRenewalScheduler(db)
    frequency = scheduler.infer_payroll_frequency(borrower_id)

    return {
        "borrower_id": borrower_id,
        "inferred_frequency": frequency.value if frequency else None,
        "inferred": frequency is not None,
    }


@router.post("/payroll-frequency/{loan_id}")
async def update_payroll_frequency(
    loan_id: int,
    body: UpdatePayrollFrequencyBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update payroll frequency for a loan's paystub requests."""
    _verify_loan_tenant(db, loan_id, current_user)
    try:
        frequency = PayrollFrequency(body.frequency)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid frequency. Must be one of: {[f.value for f in PayrollFrequency]}"
        )

    scheduler = AutoRenewalScheduler(db)
    updated = scheduler.update_payroll_frequency(
        loan_id=loan_id,
        borrower_id=body.borrower_id,
        frequency=frequency,
    )

    return {
        "loan_id": loan_id,
        "borrower_id": body.borrower_id,
        "frequency": frequency.value,
        "requests_updated": updated,
    }


# =============================================================================
# Templates
# =============================================================================

@router.get("/templates")
async def list_templates(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """List available needs list templates."""
    query = db.query(NeedsListTemplate)
    if active_only:
        query = query.filter(NeedsListTemplate.is_active == True)

    templates = query.order_by(NeedsListTemplate.name).all()

    return {
        "total": len(templates),
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "loan_programs": _safe_json_loads(t.loan_programs),
                "occupancy_types": _safe_json_loads(t.occupancy_types),
                "income_types": _safe_json_loads(t.income_types),
                "is_active": t.is_active,
                "version": t.version,
            }
            for t in templates
        ],
    }


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get a specific needs list template."""
    template = db.query(NeedsListTemplate).filter(
        NeedsListTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "slug": template.slug,
        "description": template.description,
        "loan_programs": _safe_json_loads(template.loan_programs),
        "occupancy_types": _safe_json_loads(template.occupancy_types),
        "income_types": _safe_json_loads(template.income_types),
        "request_templates": _safe_json_loads(template.request_templates),
        "is_active": template.is_active,
        "version": template.version,
    }


# =============================================================================
# Events / Audit Log
# =============================================================================

@router.get("/events/{loan_id}")
async def get_loan_events(
    loan_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get document policy events for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    events = db.query(DocPolicyEvent).filter(
        DocPolicyEvent.loan_id == loan_id
    ).order_by(
        DocPolicyEvent.created_at.desc()
    ).limit(limit).all()

    return {
        "loan_id": loan_id,
        "total": len(events),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type.value,
                "request_id": e.request_id,
                "document_id": e.document_id,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


# =============================================================================
# Applicant Views - Dashboard Endpoints
# =============================================================================

@router.get("/applicants/pending-review")
async def get_applicants_with_pending_review(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get all applicants/loans that have documents pending review.
    Returns grouped by loan with summary of pending documents.
    """
    # Default empty response
    default_response = {
        "total": 0,
        "page": page,
        "limit": limit,
        "total_pages": 0,
        "applicants": [],
    }

    try:
        from sqlalchemy import func, distinct
        from models.purl import PURLLoan, PURLWorkspace
        from database.models.lead_loan import Loan

        # Tenant isolation
        org_id = getattr(current_user, 'organization_id', None)
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

        # Build base filters
        pending_filters = [SmartDocument.status == 'PENDING_REVIEW']

        # Add tenant isolation - filter by loans that belong to user's organization
        if not is_platform_admin and org_id:
            org_loan_ids = db.query(Loan.id).filter(Loan.organization_id == org_id).subquery()
            pending_filters.append(SmartDocument.loan_id.in_(org_loan_ids))

        # Get loans with pending documents
        pending_docs_query = db.query(
            SmartDocument.loan_id,
            func.count(SmartDocument.id).label('pending_count'),
            func.min(SmartDocument.uploaded_at).label('oldest_upload')
        ).filter(
            *pending_filters
        ).group_by(SmartDocument.loan_id)

        # Get total count
        total_query = db.query(func.count(distinct(SmartDocument.loan_id))).filter(
            *pending_filters
        ).scalar() or 0

        # Paginate
        offset = (page - 1) * limit
        pending_loans = pending_docs_query.order_by(
            func.min(SmartDocument.uploaded_at).asc()
        ).offset(offset).limit(limit).all()

        # Prefetch loans and workspaces in bulk to avoid N+1
        loan_ids = [row[0] for row in pending_loans]
        loans_by_id = {}
        workspaces_by_id = {}
        if loan_ids:
            all_loans = db.query(PURLLoan).filter(PURLLoan.id.in_(loan_ids)).all()
            loans_by_id = {l.id: l for l in all_loans}
            ws_ids = [l.workspace_id for l in all_loans if l.workspace_id]
            if ws_ids:
                all_ws = db.query(PURLWorkspace).filter(PURLWorkspace.id.in_(ws_ids)).all()
                workspaces_by_id = {w.id: w for w in all_ws}

            all_pending_docs = db.query(SmartDocument).filter(
                SmartDocument.loan_id.in_(loan_ids),
                SmartDocument.status == 'PENDING_REVIEW',
            ).all()
        else:
            all_pending_docs = []

        docs_by_loan = {}
        for doc in all_pending_docs:
            docs_by_loan.setdefault(doc.loan_id, []).append(doc)

        applicants = []
        for loan_id, pending_count, oldest_upload in pending_loans:
            loan = loans_by_id.get(loan_id)
            workspace = workspaces_by_id.get(loan.workspace_id) if loan and loan.workspace_id else None

            applicants.append({
                "loan_id": loan_id,
                "loan_number": loan.loan_number if loan else None,
                "borrower_name": workspace.display_name if workspace else f"Loan {loan_id}",
                "loan_purpose": loan.loan_purpose if loan else None,
                "pending_count": pending_count,
                "oldest_upload": oldest_upload.isoformat() if oldest_upload else None,
                "documents": [
                    {
                        "id": doc.id,
                        "file_name": doc.original_filename or doc.file_name,
                        "doc_type": doc.doc_type.value if doc.doc_type else None,
                        "uploaded_at": (doc.uploaded_at or doc.created_at).isoformat() if (doc.uploaded_at or doc.created_at) else None,
                    }
                    for doc in docs_by_loan.get(loan_id, [])
                ],
            })

        return {
            "total": total_query,
            "page": page,
            "limit": limit,
            "total_pages": (total_query + limit - 1) // limit,
            "applicants": applicants,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching applicants with pending review")
        raise HTTPException(status_code=500, detail="Failed to fetch pending review data")


@router.get("/applicants/outstanding-docs")
async def get_applicants_with_outstanding_docs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get all applicants/loans that have outstanding document requests (needs list items not fulfilled).
    Returns grouped by loan with summary of outstanding requirements.
    """
    from sqlalchemy import func, distinct, case
    from models.purl import PURLLoan, PURLWorkspace
    from database.models.lead_loan import Loan

    # Tenant isolation
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    # Build filter for outstanding requests
    outstanding_filter = [DocumentRequest.status == RequestStatus.OPEN]

    # Add tenant isolation - filter by loans that belong to user's organization
    if not is_platform_admin and org_id:
        # Subquery to get loan_ids that belong to user's organization
        org_loan_ids = db.query(Loan.id).filter(Loan.organization_id == org_id).subquery()
        outstanding_filter.append(DocumentRequest.loan_id.in_(org_loan_ids))

    if include_overdue_only:
        outstanding_filter.append(DocumentRequest.due_date < func.now())

    # Get loans with outstanding requests
    # Use case() for conditional counting since func.count().filter() isn't valid
    overdue_case = case(
        (DocumentRequest.due_date < func.now(), 1),
        else_=0
    )

    outstanding_query = db.query(
        DocumentRequest.loan_id,
        func.count(DocumentRequest.id).label('outstanding_count'),
        func.sum(overdue_case).label('overdue_count'),
        func.min(DocumentRequest.due_date).label('nearest_due')
    ).filter(
        *outstanding_filter
    ).group_by(DocumentRequest.loan_id)

    # Get total count
    total_query = db.query(func.count(distinct(DocumentRequest.loan_id))).filter(
        *outstanding_filter
    ).scalar() or 0

    # Paginate - prioritize by overdue and nearest due date
    offset = (page - 1) * limit
    outstanding_loans = outstanding_query.order_by(
        func.sum(overdue_case).desc(),
        func.min(DocumentRequest.due_date).asc().nullslast()
    ).offset(offset).limit(limit).all()

    # Prefetch loans, workspaces, contacts in bulk to avoid N+1
    loan_ids = [row[0] for row in outstanding_loans]
    loans_by_id = {}
    workspaces_by_id = {}
    contacts_by_ws = {}

    if loan_ids:
        all_loans = db.query(PURLLoan).filter(PURLLoan.id.in_(loan_ids)).all()
        loans_by_id = {l.id: l for l in all_loans}
        ws_ids = [l.workspace_id for l in all_loans if l.workspace_id]
        if ws_ids:
            all_ws = db.query(PURLWorkspace).filter(PURLWorkspace.id.in_(ws_ids)).all()
            workspaces_by_id = {w.id: w for w in all_ws}
            from models.purl import PURLContact
            all_contacts = db.query(PURLContact).filter(
                PURLContact.workspace_id.in_(ws_ids),
                PURLContact.contact_type == 'borrower',
            ).all()
            for c in all_contacts:
                contacts_by_ws[c.workspace_id] = c

        # Prefetch all open requests for these loans
        all_requests = db.query(DocumentRequest).filter(
            DocumentRequest.loan_id.in_(loan_ids),
            DocumentRequest.status == RequestStatus.OPEN,
        ).order_by(DocumentRequest.priority.desc(), DocumentRequest.due_date.asc().nullslast()).all()

        # Prefetch received counts in single query
        received_rows = db.query(
            DocumentRequest.loan_id,
            func.count(DocumentRequest.id),
        ).filter(
            DocumentRequest.loan_id.in_(loan_ids),
            DocumentRequest.status != RequestStatus.OPEN,
        ).group_by(DocumentRequest.loan_id).all()
        received_by_loan = dict(received_rows)
    else:
        all_requests = []
        received_by_loan = {}

    reqs_by_loan = {}
    for req in all_requests:
        reqs_by_loan.setdefault(req.loan_id, []).append(req)

    applicants = []
    for loan_id, outstanding_count, overdue_count, nearest_due in outstanding_loans:
        loan = loans_by_id.get(loan_id)
        workspace = workspaces_by_id.get(loan.workspace_id) if loan and loan.workspace_id else None

        borrower_name = None
        if workspace and workspace.display_name:
            borrower_name = workspace.display_name
        elif loan and loan.workspace_id:
            contact = contacts_by_ws.get(loan.workspace_id)
            if contact:
                borrower_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
        if not borrower_name:
            borrower_name = f"Loan {loan_id}"

        requests = reqs_by_loan.get(loan_id, [])

        applicants.append({
            "loan_id": loan_id,
            "loan_number": loan.loan_number if loan else None,
            "borrower_name": borrower_name,
            "loan_purpose": loan.loan_purpose if loan else None,
            "outstanding_count": outstanding_count,
            "received_count": received_by_loan.get(loan_id, 0),
            "overdue_count": overdue_count or 0,
            "nearest_due": nearest_due.isoformat() if nearest_due else None,
            "requests": [
                {
                    "id": req.id,
                    "title": req.title,
                    "doc_type": req.doc_type.value if req.doc_type else None,
                    "priority": req.priority.value if req.priority else "NORMAL",
                    "due_date": req.due_date.isoformat() if req.due_date else None,
                    "is_overdue": req.due_date and req.due_date < datetime.now(timezone.utc),
                }
                for req in requests
            ],
        })

    return {
        "total": total_query,
        "page": page,
        "limit": limit,
        "total_pages": (total_query + limit - 1) // limit,
        "applicants": applicants,
    }


@router.get("/dashboard/summary")
async def get_document_dashboard_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get summary statistics for the document management dashboard.
    """
    from sqlalchemy import func
    from database.models.lead_loan import Loan

    # Tenant isolation
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    # Build tenant-scoped loan ID subquery
    if not is_platform_admin and org_id:
        org_loan_ids = db.query(Loan.id).filter(Loan.organization_id == org_id).subquery()
        doc_tenant_filter = [SmartDocument.loan_id.in_(org_loan_ids)]
        req_tenant_filter = [DocumentRequest.loan_id.in_(org_loan_ids)]
    else:
        doc_tenant_filter = []
        req_tenant_filter = []

    # Pending review count
    pending_review = db.query(func.count(SmartDocument.id)).filter(
        SmartDocument.status == 'PENDING_REVIEW',
        *doc_tenant_filter,
    ).scalar() or 0

    # Pending review by unique loans
    pending_review_loans = db.query(func.count(func.distinct(SmartDocument.loan_id))).filter(
        SmartDocument.status == 'PENDING_REVIEW',
        *doc_tenant_filter,
    ).scalar() or 0

    # Outstanding requests
    outstanding = db.query(func.count(DocumentRequest.id)).filter(
        DocumentRequest.status == RequestStatus.OPEN,
        *req_tenant_filter,
    ).scalar() or 0

    # Outstanding by unique loans
    outstanding_loans = db.query(func.count(func.distinct(DocumentRequest.loan_id))).filter(
        DocumentRequest.status == RequestStatus.OPEN,
        *req_tenant_filter,
    ).scalar() or 0

    # Overdue requests
    overdue = db.query(func.count(DocumentRequest.id)).filter(
        DocumentRequest.status == RequestStatus.OPEN,
        DocumentRequest.due_date < func.now(),
        *req_tenant_filter,
    ).scalar() or 0

    # Documents processed today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    processed_today = db.query(func.count(SmartDocument.id)).filter(
        SmartDocument.reviewed_at >= today_start,
        *doc_tenant_filter,
    ).scalar() or 0

    return {
        "pending_review": {
            "documents": pending_review,
            "applicants": pending_review_loans,
        },
        "outstanding_requests": {
            "total": outstanding,
            "applicants": outstanding_loans,
            "overdue": overdue,
        },
        "activity": {
            "processed_today": processed_today,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Loans for Smart Docs (All Active Loans)
# =============================================================================

@router.get("/loans")
async def get_smart_docs_loans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    stage: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get all loans AND leads with document requests for Smart Docs dashboard.

    This endpoint returns:
    1. All loans in active stages for document tracking purposes.
    2. Leads that have smart_document_requests (created via the lead profile's Smart Docs tab).

    Each result includes a 'record_type' field ('loan' or 'lead') so the frontend
    can distinguish them and navigate to the correct profile page.
    """
    from sqlalchemy import text

    try:
        # Tenant isolation
        org_id = getattr(current_user, 'organization_id', None)
        is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

        # Build WHERE clause for active loans (exclude funded)
        loan_where_clauses = ["l.stage != 'Funded'"]
        params = {"skip": skip, "limit": limit}

        # Add tenant isolation filter
        if not is_platform_admin and org_id:
            loan_where_clauses.append("l.organization_id = :org_id")
            params["org_id"] = org_id

        # Filter by specific stage if provided
        if stage:
            loan_where_clauses.append("l.stage = :stage")
            params["stage"] = stage

        # Search filter
        if search:
            params["search"] = f"%{search}%"

        loan_where_sql = " AND ".join(loan_where_clauses) if loan_where_clauses else "1=1"

        # Add search to loan query
        loan_search_clause = ""
        if search:
            loan_search_clause = " AND (l.borrower_name ILIKE :search OR l.loan_number ILIKE :search OR l.borrower_email ILIKE :search)"

        # Main loans query
        loans_sql = f"""
            SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email, l.borrower_phone,
                   l.coborrower_name, l.co_borrower_email,
                   l.stage, l.program, l.amount, l.rate,
                   l.closing_date, l.days_in_stage, l.sla_status, l.created_at,
                   l.loan_officer_name, l.loan_officer_email, l.processor, l.processor_email,
                   l.underwriter, l.underwriter_email, l.closer, l.closer_email,
                   l.property_address, l.loan_type, l.purchase_price, l.down_payment,
                   'loan' AS record_type
            FROM loans l
            WHERE {loan_where_sql}{loan_search_clause}
        """

        # Check if smart_document_requests table exists before trying to query leads
        table_check = db.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'smart_document_requests')"
        )).scalar()

        leads_sql = ""
        if table_check:
            # Build WHERE clause for leads with document requests
            lead_where_clauses = []
            if not is_platform_admin and org_id:
                lead_where_clauses.append("ld.organization_id = :org_id")
            if stage:
                lead_where_clauses.append("ld.stage = :stage")

            lead_where_sql = " AND ".join(lead_where_clauses) if lead_where_clauses else "1=1"

            # Add search to lead query
            lead_search_clause = ""
            if search:
                lead_search_clause = " AND (ld.name ILIKE :search OR ld.first_name ILIKE :search OR ld.last_name ILIKE :search OR ld.email ILIKE :search)"

            # Leads with document requests — exclude any lead whose ID also matches
            # a loan ID that already appears in the loans query (since doc requests
            # use the same loan_id column for both)
            leads_sql = f"""
                UNION ALL
                SELECT ld.id,
                       ld.loan_number,
                       COALESCE(ld.name, TRIM(COALESCE(ld.first_name, '') || ' ' || COALESCE(ld.last_name, ''))) AS borrower_name,
                       ld.email AS borrower_email,
                       ld.phone AS borrower_phone,
                       ld.co_applicant_name AS coborrower_name,
                       ld.co_applicant_email AS co_borrower_email,
                       ld.stage, NULL AS program, ld.preapproval_amount AS amount, NULL AS rate,
                       NULL AS closing_date, NULL AS days_in_stage, NULL AS sla_status, ld.created_at,
                       NULL AS loan_officer_name, NULL AS loan_officer_email,
                       NULL AS processor, NULL AS processor_email,
                       NULL AS underwriter, NULL AS underwriter_email,
                       NULL AS closer, NULL AS closer_email,
                       NULL AS property_address, ld.loan_type, NULL AS purchase_price, NULL AS down_payment,
                       'lead' AS record_type
                FROM leads ld
                INNER JOIN (
                    SELECT DISTINCT loan_id FROM smart_document_requests
                ) sdr ON sdr.loan_id = ld.id
                WHERE {lead_where_sql}{lead_search_clause}
                  AND ld.id NOT IN (SELECT id FROM loans)
            """

        combined_sql = f"""
            SELECT * FROM (
                {loans_sql}
                {leads_sql}
            ) combined
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :skip
        """

        results = db.execute(text(combined_sql), params).fetchall()

        # Convert to list of dicts
        loans = []
        for row in results:
            row_dict = dict(row._mapping)
            # Normalize stage
            stage_val = row_dict.get('stage', '')
            if stage_val:
                row_dict['stage'] = str(stage_val).upper()
            else:
                row_dict['stage'] = 'PROCESSING'
            loans.append(row_dict)

        # Get total count for pagination (same UNION structure without LIMIT/OFFSET)
        count_leads_sql = ""
        if table_check and leads_sql:
            count_leads_sql = leads_sql

        count_sql = f"""
            SELECT COUNT(*) FROM (
                {loans_sql}
                {count_leads_sql}
            ) combined
        """
        total = db.execute(text(count_sql), params).scalar() or 0

        return {
            "loans": loans,
            "total": total,
            "page": skip // limit + 1 if limit > 0 else 1,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
        }
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching loans for Smart Docs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Queue View Endpoints
# =============================================================================

@router.get("/queue")
async def get_document_queue(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sla_status: Optional[str] = Query(default=None, description="Filter by SLA status: GOOD, AT_RISK, BREACHED"),
    search: Optional[str] = Query(default=None, description="Search by borrower name or loan number"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get the prioritized document queue.

    Returns client-centric view with:
    - completion_percentage (received_valid / requested)
    - sla_status (GOOD, AT_RISK, BREACHED)
    - has_sla_breach boolean
    - last_activity timestamp

    Sorted by: SLA breaches first, then lowest completion, then most recent activity
    """
    from services.smart_docs.queue_service import QueueService

    # Tenant isolation — organization_id filtering is enforced inside QueueService
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    queue_service = QueueService(db, organization_id=org_id)
    result = queue_service.get_queue(
        page=page,
        limit=limit,
        filter_sla_status=sla_status,
        search_query=search,
    )

    return result


@router.get("/queue/summary")
async def get_queue_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get summary statistics for the document queue."""
    try:
        from services.smart_docs.queue_service import QueueService

        # Tenant isolation — organization_id filtering is enforced inside QueueService
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        queue_service = QueueService(db, organization_id=org_id)
        result = queue_service.get_queue_summary()

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Queue summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Queue service error")


@router.get("/queue/{loan_id}")
async def get_client_queue_detail(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get detailed queue information for a specific client."""
    _verify_loan_tenant(db, loan_id, current_user)
    from services.smart_docs.queue_service import QueueService

    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    queue_service = QueueService(db, organization_id=org_id)
    result = queue_service.get_client_queue_detail(loan_id)

    if not result:
        raise HTTPException(status_code=404, detail="Client not found in queue")

    # Get org_id for S3 presigned URLs
    org_id = getattr(current_user, 'organization_id', None)

    # Enrich each request with uploaded document info
    for req in result.get("requests", []):
        request_id = req.get("id")
        if request_id:
            # Get uploaded documents for this request (exclude deleted/superseded)
            uploaded_docs = db.query(SmartDocument).filter(
                SmartDocument.request_id == request_id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
            ).order_by(SmartDocument.created_at.desc()).all()

            if uploaded_docs:
                latest_doc = uploaded_docs[0]
                req["document_id"] = latest_doc.id
                req["filename"] = latest_doc.file_name
                req["uploaded_at"] = latest_doc.created_at.isoformat() if latest_doc.created_at else None

                # Generate presigned URL for viewing - verify file exists first
                if latest_doc.storage_key:
                    s3_service = get_smart_docs_s3_service()
                    if s3_service.is_available:
                        # Check if file actually exists in S3 before generating URL
                        if s3_service.file_exists(latest_doc.storage_key):
                            url_result = s3_service.get_presigned_download_url(
                                storage_key=latest_doc.storage_key,
                                file_name=latest_doc.file_name,
                                expires_in=3600,  # 1 hour
                                inline=True,  # Use inline disposition for iframe viewing
                                organization_id=org_id  # Pass org_id for tenant validation
                            )
                            if url_result.get("success"):
                                req["file_url"] = url_result["presigned_url"]
                                req["s3_url"] = url_result["presigned_url"]
                        else:
                            # File doesn't exist in S3 - mark as storage error
                            req["storage_error"] = True
                            req["storage_error_message"] = "Document file not found in storage. Please re-upload."
                            logger.warning(f"S3 file not found for document {latest_doc.id}: {latest_doc.storage_key}")

                req["document_id"] = latest_doc.id
                req["doc_date"] = latest_doc.doc_date.isoformat() if latest_doc.doc_date else None
                req["expiration_date"] = latest_doc.doc_expires_at.isoformat() if latest_doc.doc_expires_at else None

    # Also add all_requests for frontend compatibility
    result["all_requests"] = result.get("requests", [])

    return result


# =============================================================================
# Client Reminder Settings Endpoints
# =============================================================================

@router.get("/reminders/{loan_id}")
async def get_reminder_settings(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get reminder settings for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings

    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        # Return defaults if no settings exist
        return {
            "loan_id": loan_id,
            "reminders_enabled": True,
            "reminder_frequency_hours": 72,
            "last_reminder_sent_at": None,
            "reminder_count": 0,
        }

    return {
        "loan_id": settings.loan_id,
        "reminders_enabled": settings.reminders_enabled,
        "reminder_frequency_hours": settings.reminder_frequency_hours,
        "last_reminder_sent_at": settings.last_reminder_sent_at.isoformat() if settings.last_reminder_sent_at else None,
        "reminder_count": settings.reminder_count,
    }


@router.put("/reminders/{loan_id}")
async def update_reminder_settings(
    loan_id: int,
    body: ReminderSettingsBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update reminder settings for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings

    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        settings = ClientReminderSettings(
            loan_id=loan_id,
            reminders_enabled=body.reminders_enabled,
            reminder_frequency_hours=body.reminder_frequency_hours,
        )
        db.add(settings)
    else:
        settings.reminders_enabled = body.reminders_enabled
        settings.reminder_frequency_hours = body.reminder_frequency_hours
        settings.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(settings)

    return {
        "loan_id": settings.loan_id,
        "reminders_enabled": settings.reminders_enabled,
        "reminder_frequency_hours": settings.reminder_frequency_hours,
        "updated": True,
    }


@router.post("/reminders/{loan_id}/send")
async def send_reminder(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Manually trigger a reminder for a loan.

    Updates last_reminder_sent_at and increments reminder_count.
    """
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings
    from services.smart_docs.notification_service import SmartDocsNotificationService

    # Get pending requests
    pending_requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == loan_id,
        DocumentRequest.is_active == True,
        DocumentRequest.status == RequestStatus.OPEN
    ).all()

    if not pending_requests:
        return {"sent": False, "message": "No pending document requests"}

    # Get or create reminder settings
    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        settings = ClientReminderSettings(loan_id=loan_id)
        db.add(settings)

    # Get borrower info from loan
    from sqlalchemy import text
    loan_info = db.execute(text("""
        SELECT borrower_name, borrower_email FROM loans WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan_info or not loan_info.borrower_email:
        return {"sent": False, "message": "Borrower email not found"}

    # Try to send reminder
    sent = False
    try:
        notification_service = SmartDocsNotificationService(db)
        sent = notification_service.send_bulk_request_notification(
            requests=pending_requests,
            borrower_email=loan_info.borrower_email,
            borrower_name=loan_info.borrower_name or "Borrower",
        )
    except Exception as e:
        logger.exception("Failed to send reminder notification for loan %s", loan_id)
        sent = False

    if sent:
        settings.last_reminder_sent_at = datetime.now(timezone.utc)
        settings.reminder_count = (settings.reminder_count or 0) + 1
        db.commit()

    return {
        "sent": sent,
        "documents_reminded": len(pending_requests),
        "reminder_count": settings.reminder_count,
    }


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "smart-docs",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
